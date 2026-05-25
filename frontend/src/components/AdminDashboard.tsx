import { useEffect, useRef, useState } from 'react'

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
  escalated: number
  pending: number
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
  onNewTicket: () => void
  onToast?: (message: string, variant?: 'success' | 'error' | 'info') => void
}

const STATUS_CONFIG: Record<string, { badge: string; dot: string }> = {
  resolved:  { badge: 'bg-emerald-50 text-emerald-700 border-emerald-200', dot: 'bg-emerald-500' },
  escalated: { badge: 'bg-amber-50 text-amber-700 border-amber-200',       dot: 'bg-amber-500'   },
  pending:   { badge: 'bg-indigo-50 text-indigo-700 border-indigo-200',    dot: 'bg-indigo-400'  },
}

const CATEGORY_LABEL: Record<string, string> = {
  password_reset: 'Password Reset', access_request: 'Access Request',
  software_install: 'Software Install', incident_report: 'Incident',
  leave_approval: 'Leave', unknown: 'Unknown',
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60_000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({ label, value, color, icon }: {
  label: string; value: number
  color: 'slate' | 'emerald' | 'amber' | 'indigo'
  icon: React.ReactNode
}) {
  const styles = {
    slate:   { card: 'bg-white border-slate-200',           num: 'text-slate-900', sub: 'text-slate-400', icon: 'bg-slate-100 text-slate-500'     },
    emerald: { card: 'bg-emerald-50 border-emerald-200',    num: 'text-emerald-800', sub: 'text-emerald-500', icon: 'bg-emerald-100 text-emerald-600' },
    amber:   { card: 'bg-amber-50 border-amber-200',        num: 'text-amber-800',   sub: 'text-amber-500',   icon: 'bg-amber-100 text-amber-600'     },
    indigo:  { card: 'bg-indigo-50 border-indigo-200',      num: 'text-indigo-800',  sub: 'text-indigo-500',  icon: 'bg-indigo-100 text-indigo-600'   },
  }
  const s = styles[color]
  return (
    <div className={`rounded-2xl border px-4 py-4 ${s.card}`}>
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center mb-3 ${s.icon}`}>{icon}</div>
      <p className={`text-2xl font-bold tracking-tight ${s.num}`}>{value}</p>
      <p className={`text-xs font-semibold mt-0.5 ${s.sub}`}>{label}</p>
    </div>
  )
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

// ── Resolve panel ─────────────────────────────────────────────────────────────

function ResolvePanel({ ticket, token, onDone, onToast }: {
  ticket: TicketRow; token: string
  onDone: (updated: TicketRow) => void
  onToast?: (msg: string, v?: 'success' | 'error' | 'info') => void
}) {
  const [note, setNote] = useState(ticket.admin_note || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [comments, setComments] = useState<Comment[]>([])
  const [newComment, setNewComment] = useState('')
  const [addingComment, setAddingComment] = useState(false)
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  useEffect(() => {
    fetch(`/admin/tickets/${ticket.ticket_id}/comments`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : { comments: [] })
      .then(d => setComments(d.comments || []))
  }, [ticket.ticket_id])

  async function handleResolve(newStatus: 'resolved' | 'escalated') {
    setSaving(true); setError(null)
    try {
      const r = await fetch(`/admin/tickets/${ticket.ticket_id}`, {
        method: 'PATCH', headers,
        body: JSON.stringify({ status: newStatus, admin_note: note || undefined }),
      })
      if (!r.ok) throw new Error((await r.json()).detail?.error ?? `HTTP ${r.status}`)
      const result = await r.json()
      onDone(result)
      onToast?.(newStatus === 'resolved' ? 'Ticket marked as resolved' : 'Ticket escalated', 'success')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update')
    } finally {
      setSaving(false)
    }
  }

  async function handleAddComment() {
    if (!newComment.trim()) return
    setAddingComment(true)
    try {
      const r = await fetch(`/admin/tickets/${ticket.ticket_id}/comments`, {
        method: 'POST', headers,
        body: JSON.stringify({ content: newComment }),
      })
      if (r.ok) { const c = await r.json(); setComments(prev => [...prev, c]); setNewComment('') }
    } finally {
      setAddingComment(false)
    }
  }

  return (
    <div className="mt-3 pt-4 border-t border-slate-100 space-y-4 fade-in">
      {/* Resolution note */}
      <div>
        <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-widest mb-2">Resolution note</label>
        <textarea
          rows={2}
          value={note}
          onChange={e => setNote(e.target.value)}
          placeholder="Describe how this was resolved…"
          className="w-full text-sm border border-slate-200 rounded-xl px-3.5 py-2.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none hover:border-slate-300 transition-shadow bg-slate-50/50 focus:bg-white"
        />
      </div>
      {error && <p className="text-xs text-red-600 font-medium">{error}</p>}
      <div className="flex gap-2">
        <button
          onClick={() => handleResolve('resolved')}
          disabled={saving}
          className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-xl px-3 py-2.5 transition-colors disabled:opacity-40 shadow-sm"
        >
          {saving ? 'Saving…' : (
            <span className="flex items-center justify-center gap-1.5">
              <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M16.707 5.293a1 1 0 00-1.414 0L8 12.586 4.707 9.293a1 1 0 00-1.414 1.414l4 4a1 1 0 001.414 0l8-8a1 1 0 000-1.414z" clipRule="evenodd" />
              </svg>
              Mark resolved
            </span>
          )}
        </button>
        {ticket.status !== 'escalated' && (
          <button
            onClick={() => handleResolve('escalated')}
            disabled={saving}
            className="flex-1 bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold rounded-xl px-3 py-2.5 transition-colors disabled:opacity-40 shadow-sm"
          >
            Escalate
          </button>
        )}
      </div>

      {/* Comments */}
      <div>
        <p className="text-[11px] font-bold text-slate-500 uppercase tracking-widest mb-2">
          Comments {comments.length > 0 && <span className="text-slate-400">({comments.length})</span>}
        </p>
        {comments.length > 0 && (
          <div className="space-y-2 mb-3 max-h-40 overflow-y-auto">
            {comments.map(c => (
              <div key={c.id} className="bg-slate-50 border border-slate-100 rounded-xl px-3.5 py-2.5">
                <p className="text-xs text-slate-700 leading-relaxed">{c.content}</p>
                <p className="text-[10px] text-slate-400 mt-1 font-medium">{relativeTime(c.created_at)}</p>
              </div>
            ))}
          </div>
        )}
        <div className="flex gap-2">
          <input
            type="text"
            value={newComment}
            onChange={e => setNewComment(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAddComment()}
            placeholder="Add a comment…"
            className="flex-1 text-xs border border-slate-200 rounded-xl px-3.5 py-2.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 hover:border-slate-300 transition-shadow bg-slate-50/50 focus:bg-white"
          />
          <button
            onClick={handleAddComment}
            disabled={addingComment || !newComment.trim()}
            className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-xl px-3.5 py-2.5 disabled:opacity-40 transition-colors shadow-sm"
          >
            Post
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

function KnowledgeBasePanel({ token, onToast }: {
  token: string
  onToast?: (msg: string, v?: 'success' | 'error' | 'info') => void
}) {
  const [docs, setDocs] = useState<KbDoc[]>([])
  const [loading, setLoading] = useState(true)
  const [mode, setMode] = useState<'write' | 'upload'>('write')

  // write mode
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [writeError, setWriteError] = useState<string | null>(null)

  // upload mode
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadTitle, setUploadTitle] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
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

  function handleFileSelect(file: File) {
    setUploadError(null)
    const ext = fileExt(file.name)
    if (!['pdf', 'txt', 'md', 'docx'].includes(ext)) {
      setUploadError(`Unsupported file type ".${ext}". Use PDF, TXT, MD, or DOCX.`)
      return
    }
    if (file.size > KB_MAX_MB * 1024 * 1024) {
      setUploadError(`File is too large (${(file.size / 1_048_576).toFixed(1)} MB). Max ${KB_MAX_MB} MB.`)
      return
    }
    setUploadFile(file)
    if (!uploadTitle.trim()) setUploadTitle(file.name.replace(/\.[^.]+$/, ''))
  }

  async function handleUpload() {
    if (!uploadFile) return
    setUploading(true); setUploadError(null)
    try {
      const form = new FormData()
      form.append('file', uploadFile)
      if (uploadTitle.trim()) form.append('title', uploadTitle.trim())
      const r = await fetch('/admin/kb/upload', { method: 'POST', headers: authHeaders, body: form })
      if (!r.ok) {
        const body = await r.json().catch(() => ({}))
        throw new Error(body?.detail?.error ?? `HTTP ${r.status}`)
      }
      const doc: KbDoc = await r.json()
      setDocs(prev => [doc, ...prev])
      setUploadFile(null); setUploadTitle('')
      if (fileInputRef.current) fileInputRef.current.value = ''
      onToast?.(`"${doc.title}" added to knowledge base`, 'success')
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
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
                  onClick={() => { setMode(m); setWriteError(null); setUploadError(null) }}
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
            {/* Drop zone */}
            <div
              onDragOver={e => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={e => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) handleFileSelect(f) }}
              onClick={() => fileInputRef.current?.click()}
              className={`relative cursor-pointer rounded-xl border-2 border-dashed px-5 py-8 text-center transition-all ${
                dragging
                  ? 'border-indigo-400 bg-indigo-50'
                  : uploadFile
                  ? 'border-emerald-300 bg-emerald-50/50'
                  : 'border-slate-200 hover:border-indigo-300 hover:bg-slate-50'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept={KB_ACCEPT}
                className="hidden"
                onChange={e => { const f = e.target.files?.[0]; if (f) handleFileSelect(f) }}
              />
              {uploadFile ? (
                <div className="flex items-center justify-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-emerald-100 flex items-center justify-center flex-shrink-0">
                    <svg className="w-5 h-5 text-emerald-600" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                      <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div className="text-left min-w-0">
                    <p className="text-sm font-semibold text-slate-800 truncate max-w-[200px]">{uploadFile.name}</p>
                    <p className="text-xs text-slate-400">{(uploadFile.size / 1024).toFixed(0)} KB · Click to change</p>
                  </div>
                </div>
              ) : (
                <>
                  <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
                    <svg className="w-5 h-5 text-slate-400" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                      <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM6.293 6.707a1 1 0 010-1.414l3-3a1 1 0 011.414 0l3 3a1 1 0 01-1.414 1.414L11 5.414V13a1 1 0 11-2 0V5.414L7.707 6.707a1 1 0 01-1.414 0z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <p className="text-sm font-semibold text-slate-700">Drop file here or click to browse</p>
                  <p className="text-xs text-slate-400 mt-1">PDF, TXT, MD, DOCX — up to {KB_MAX_MB} MB</p>
                </>
              )}
            </div>

            {/* Title override */}
            {uploadFile && (
              <input
                type="text"
                value={uploadTitle}
                onChange={e => setUploadTitle(e.target.value)}
                placeholder="Document title (optional — defaults to filename)"
                className="w-full text-sm border border-slate-200 rounded-xl px-3.5 py-2.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 hover:border-slate-300 transition-shadow bg-slate-50/50 focus:bg-white"
              />
            )}

            {uploadError && (
              <div className="flex items-start gap-2 text-xs text-red-700 bg-red-50 border border-red-100 rounded-xl px-3.5 py-2.5">
                <svg className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                  <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
                </svg>
                {uploadError}
              </div>
            )}

            <button
              onClick={handleUpload}
              disabled={uploading || !uploadFile}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-xl px-4 py-2.5 transition-colors disabled:opacity-40 shadow-sm"
            >
              {uploading ? (
                <><svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>Uploading…</>
              ) : (
                <><svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM6.293 6.707a1 1 0 010-1.414l3-3a1 1 0 011.414 0l3 3a1 1 0 01-1.414 1.414L11 5.414V13a1 1 0 11-2 0V5.414L7.707 6.707a1 1 0 01-1.414 0z" clipRule="evenodd" /></svg>Upload & extract</>
              )}
            </button>
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

function EscalatedQueuePanel({ token, onToast }: {
  token: string
  onToast?: (msg: string, v?: 'success' | 'error' | 'info') => void
}) {
  const [tickets, setTickets] = useState<TicketRow[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [priorityFilter, setPriorityFilter] = useState<string>('')

  useEffect(() => {
    fetch('/admin/tickets?status=escalated&limit=100', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : { tickets: [] })
      .then(d => { setTickets(d.tickets || []); setLoading(false) })
  }, [token])

  function handleResolved(updated: TicketRow) {
    setTickets(prev => prev.filter(t => t.ticket_id !== updated.ticket_id))
    setExpandedId(null)
  }

  const filtered = priorityFilter
    ? tickets.filter(t => (t.priority ?? 'MEDIUM') === priorityFilter)
    : tickets

  const PRIORITY_FILTERS = [
    { val: '',         label: 'All' },
    { val: 'CRITICAL', label: 'Critical' },
    { val: 'HIGH',     label: 'High' },
    { val: 'MEDIUM',   label: 'Medium' },
    { val: 'LOW',      label: 'Low' },
  ]

  if (loading) return <div className="bg-white rounded-2xl border border-slate-200 h-32 animate-pulse" />

  return (
    <div className="space-y-4">
      {/* Header card */}
      <div className="bg-amber-50 border border-amber-200 rounded-2xl px-5 py-4 flex items-start gap-4">
        <div className="w-10 h-10 rounded-xl bg-amber-100 flex items-center justify-center flex-shrink-0">
          <svg className="w-5 h-5 text-amber-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
          </svg>
        </div>
        <div>
          <p className="text-sm font-bold text-amber-900">Human review required</p>
          <p className="text-xs text-amber-700 mt-0.5 leading-relaxed">
            {tickets.length === 0
              ? 'No tickets awaiting review — all clear.'
              : `${tickets.length} ticket${tickets.length !== 1 ? 's' : ''} need${tickets.length === 1 ? 's' : ''} human attention. Resolve each by adding a note and marking it done.`}
          </p>
        </div>
      </div>

      {tickets.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
          {/* Filter bar */}
          <div className="px-5 py-3.5 border-b border-slate-100 flex items-center justify-between gap-3 flex-wrap">
            <p className="text-sm font-bold text-slate-900">
              Escalated tickets
              <span className="text-slate-400 font-normal ml-2 text-xs">({filtered.length}{priorityFilter ? ` of ${tickets.length}` : ''})</span>
            </p>
            <div className="flex gap-0.5 bg-slate-100 rounded-lg p-0.5">
              {PRIORITY_FILTERS.map(({ val, label }) => (
                <button
                  key={val}
                  onClick={() => setPriorityFilter(val)}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all ${
                    priorityFilter === val ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {filtered.length === 0 ? (
            <p className="px-5 py-8 text-sm text-slate-400 text-center">No {priorityFilter.toLowerCase()} priority tickets.</p>
          ) : (
            <div className="divide-y divide-slate-100">
              {filtered.map((t) => {
                const priority = (t.priority ?? 'MEDIUM').toUpperCase()
                const pCfg = PRIORITY_CONFIG[priority] ?? PRIORITY_CONFIG.MEDIUM
                const group = t.assignee_group ?? 'tier-1-support'
                const gCfg = GROUP_CONFIG[group] ?? GROUP_CONFIG['tier-1-support']
                const isOpen = expandedId === t.ticket_id

                return (
                  <div key={t.ticket_id} className={`px-5 py-4 transition-colors ${isOpen ? 'bg-slate-50/60' : 'hover:bg-slate-50/40'}`}>
                    {/* Ticket header row */}
                    <div
                      className="flex items-start gap-3 cursor-pointer group"
                      onClick={() => setExpandedId(isOpen ? null : t.ticket_id)}
                    >
                      {/* Priority dot */}
                      <div className={`w-2 h-2 rounded-full flex-shrink-0 mt-2 ${
                        priority === 'CRITICAL' ? 'bg-red-500' :
                        priority === 'HIGH' ? 'bg-orange-400' :
                        priority === 'MEDIUM' ? 'bg-amber-400' : 'bg-slate-300'
                      }`} aria-hidden="true" />

                      <div className="flex-1 min-w-0">
                        {/* Top row: ID + badges */}
                        <div className="flex items-center gap-2 flex-wrap mb-1.5">
                          <span className="text-[10px] font-mono font-semibold text-slate-400">
                            #{t.ticket_id.slice(0, 8).toUpperCase()}
                          </span>
                          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${pCfg.badge}`}>
                            {pCfg.label}
                          </span>
                          <span className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border ${gCfg.cls}`}>
                            <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path strokeLinecap="round" strokeLinejoin="round" d={gCfg.icon} />
                            </svg>
                            {gCfg.label}
                          </span>
                          {t.category && (
                            <span className="text-[10px] font-semibold text-slate-400">{CATEGORY_LABEL[t.category] ?? t.category}</span>
                          )}
                        </div>

                        {/* Raw request text */}
                        {t.raw_text && (
                          <p className="text-sm text-slate-800 font-medium line-clamp-2 leading-snug mb-1.5">
                            {t.raw_text}
                          </p>
                        )}

                        {/* Escalation reason */}
                        {t.escalation_reason && (
                          <div className="flex items-start gap-1.5 mb-1.5">
                            <svg className="w-3.5 h-3.5 text-amber-500 flex-shrink-0 mt-0.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                              <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
                            </svg>
                            <p className="text-xs text-amber-700 leading-snug">{t.escalation_reason}</p>
                          </div>
                        )}

                        {/* Meta row */}
                        <div className="flex items-center gap-2 text-[11px] text-slate-400 flex-wrap">
                          {t.user_email && (
                            <span className="flex items-center gap-1">
                              <svg className="w-3 h-3" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                <path d="M3 4a2 2 0 00-2 2v1.161l8.441 4.221a1.25 1.25 0 001.118 0L19 7.162V6a2 2 0 00-2-2H3z" />
                                <path d="M19 8.839l-7.77 3.885a2.75 2.75 0 01-2.46 0L1 8.839V14a2 2 0 002 2h14a2 2 0 002-2V8.839z" />
                              </svg>
                              {t.user_email}
                            </span>
                          )}
                          <span>·</span>
                          <span>{relativeTime(t.created_at)}</span>
                        </div>
                      </div>

                      {/* Expand chevron */}
                      <svg
                        className={`w-4 h-4 text-slate-300 group-hover:text-slate-500 transition-all flex-shrink-0 mt-1 ${isOpen ? 'rotate-180 text-slate-500' : ''}`}
                        viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"
                      >
                        <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
                      </svg>
                    </div>

                    {/* Expanded: resolve + comment panel */}
                    {isOpen && (
                      <ResolvePanel
                        ticket={t}
                        token={token}
                        onToast={onToast}
                        onDone={(updated) => handleResolved(updated as TicketRow)}
                      />
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function AdminDashboard({ token, onNewTicket, onToast }: Props) {
  const [org, setOrg] = useState<OrgInfo | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const [members, setMembers] = useState<Member[]>([])
  const [invites, setInvites] = useState<Invite[]>([])
  const [tickets, setTickets] = useState<TicketRow[]>([])
  const [ticketTotal, setTicketTotal] = useState(0)
  const [ticketOffset, setTicketOffset] = useState(0)
  const [statusFilter, setStatusFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [expandedTicket, setExpandedTicket] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'escalated' | 'tickets' | 'members' | 'invites' | 'kb'>('escalated')
  const sseRef = useRef<EventSource | null>(null)

  const headers = { Authorization: `Bearer ${token}` }
  const LIMIT = 20

  async function loadTickets(offset: number, sf: string) {
    const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) })
    if (sf) params.set('status', sf)
    const r = await fetch(`/admin/tickets?${params}`, { headers })
    if (!r.ok) return
    const data = await r.json()
    setTickets(data.tickets)
    setTicketTotal(data.total)
    setTicketOffset(offset)
  }

  useEffect(() => {
    // JWT in query param required — EventSource API has no header support. Acceptable for internal enterprise tool.
    const sse = new EventSource(`/admin/stream?token=${encodeURIComponent(token)}`)
    sseRef.current = sse

    sse.onmessage = (e: MessageEvent) => {
      try {
        const ticket: TicketRow = JSON.parse(e.data as string)
        setTickets(prev => {
          const idx = prev.findIndex(t => t.ticket_id === ticket.ticket_id)
          if (idx >= 0) {
            const next = [...prev]
            next[idx] = { ...prev[idx], ...ticket }
            return next
          }
          return [ticket, ...prev]
        })
        fetch('/admin/stats', { headers })
          .then(r => r.ok ? r.json() : null)
          .then(d => d && setStats(d as Stats))
        if (ticket.status === 'escalated') {
          onToast?.(`New escalation from ${ticket.user_email ?? 'unknown user'}`, 'error')
        }
      } catch { /* ignore malformed events */ }
    }

    async function load() {
      setLoading(true)
      const [orgR, statsR, membersR, invitesR] = await Promise.all([
        fetch('/orgs/me', { headers }),
        fetch('/admin/stats', { headers }),
        fetch('/orgs/members', { headers }),
        fetch('/admin/invites', { headers }),
      ])
      if (orgR.ok) setOrg(await orgR.json())
      if (statsR.ok) setStats(await statsR.json())
      if (membersR.ok) setMembers((await membersR.json()).members)
      if (invitesR.ok) setInvites((await invitesR.json()).invites)
      await loadTickets(0, '')
      setLoading(false)
    }
    load()

    return () => {
      sse.close()
      sseRef.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  async function handleStatusFilter(s: string) {
    setStatusFilter(s)
    await loadTickets(0, s)
  }

  function handleTicketUpdated(updated: TicketRow) {
    setTickets(prev => prev.map(t => t.ticket_id === updated.ticket_id ? updated : t))
    if (stats) {
      fetch('/admin/stats', { headers }).then(r => r.ok ? r.json() : null).then(d => d && setStats(d))
    }
  }

  if (loading) {
    return (
      <div className="space-y-4 fade-in">
        {[1, 2, 3].map(i => <div key={i} className="bg-white rounded-2xl border border-slate-200 h-24 animate-pulse" />)}
      </div>
    )
  }

  const activeInvites = invites.filter(i => !i.used_at && (!i.expires_at || new Date(i.expires_at) > new Date())).length

  const TABS = [
    { key: 'escalated' as const, label: 'Escalated',     count: stats?.escalated ?? undefined, amber: true },
    { key: 'tickets'   as const, label: 'Tickets',        count: ticketTotal > 0 ? ticketTotal : undefined, amber: false },
    { key: 'members'   as const, label: 'Members',        count: members.length > 0 ? members.length : undefined, amber: false },
    { key: 'invites'   as const, label: 'Invites',        count: activeInvites > 0 ? activeInvites : undefined, amber: false },
    { key: 'kb'        as const, label: 'KB',             count: undefined as number | undefined, amber: false },
  ]

  const TICKET_FILTERS = [
    { val: '', label: 'All' },
    { val: 'resolved',  label: 'Resolved'  },
    { val: 'escalated', label: 'Escalated' },
    { val: 'pending',   label: 'Pending'   },
  ]

  return (
    <div className="fade-in space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="inline-flex items-center gap-1.5 text-[11px] font-bold text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-full px-2.5 py-1">
              Admin
            </span>
          </div>
          <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight">Dashboard</h2>
          {org?.name && <p className="mt-0.5 text-sm text-slate-500">{org.name}</p>}
        </div>
        <button
          onClick={onNewTicket}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl px-4 py-2.5 text-sm font-semibold transition-colors shadow-sm hover:shadow-md flex-shrink-0"
        >
          <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path d="M10.75 4.75a.75.75 0 00-1.5 0v4.5h-4.5a.75.75 0 000 1.5h4.5v4.5a.75.75 0 001.5 0v-4.5h4.5a.75.75 0 000-1.5h-4.5v-4.5z" />
          </svg>
          New ticket
        </button>
      </div>

      {/* Stats */}
      {stats && (() => {
        const resolutionRate = stats.total > 0 ? Math.round(stats.resolved / stats.total * 100) : 0
        return (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard label="Total tickets" value={stats.total} color="slate" icon={
              <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clipRule="evenodd" /></svg>
            } />
            <div className="rounded-2xl border px-4 py-4 bg-emerald-50 border-emerald-200">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center mb-3 bg-emerald-100 text-emerald-600">
                <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" /></svg>
              </div>
              <p className="text-2xl font-bold tracking-tight text-emerald-800">{stats.resolved}</p>
              <p className="text-xs font-semibold mt-0.5 text-emerald-500">Resolved</p>
              {stats.total > 0 && (
                <div className="mt-2">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] font-bold text-emerald-600">{resolutionRate}% rate</span>
                  </div>
                  <div className="h-1 bg-emerald-100 rounded-full overflow-hidden">
                    <div className="h-full bg-emerald-500 rounded-full transition-all" style={{width: `${resolutionRate}%`}} />
                  </div>
                </div>
              )}
            </div>
            <StatCard label="Escalated" value={stats.escalated} color="amber" icon={
              <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" /></svg>
            } />
            <StatCard label="Pending" value={stats.pending} color="indigo" icon={
              <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm.75-13a.75.75 0 00-1.5 0v5c0 .414.336.75.75.75h4a.75.75 0 000-1.5h-3.25V5z" clipRule="evenodd" /></svg>
            } />
          </div>
        )
      })()}

      {/* Org info strip */}
      {org && (
        <div className="bg-white rounded-2xl border border-slate-200 px-5 py-3.5 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-indigo-100 flex items-center justify-center flex-shrink-0">
              <svg className="w-4 h-4 text-indigo-600" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M4 16.5v-13h-.25a.75.75 0 010-1.5h12.5a.75.75 0 010 1.5H16v13h.25a.75.75 0 010 1.5h-3.5a.75.75 0 01-.75-.75v-2.5a.75.75 0 00-.75-.75h-2.5a.75.75 0 00-.75.75v2.5a.75.75 0 01-.75.75h-3.5a.75.75 0 010-1.5H4zm3-11a.75.75 0 01.75-.75h.5a.75.75 0 010 1.5h-.5A.75.75 0 017 5.5zm.75 2.25a.75.75 0 000 1.5h.5a.75.75 0 000-1.5h-.5zm-.75 4a.75.75 0 01.75-.75h.5a.75.75 0 010 1.5h-.5a.75.75 0 01-.75-.75zm5.25-6a.75.75 0 000 1.5h.5a.75.75 0 000-1.5h-.5zm-.75 4a.75.75 0 01.75-.75h.5a.75.75 0 010 1.5h-.5a.75.75 0 01-.75-.75z" clipRule="evenodd" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-900">{org.name}</p>
              <p className="text-xs text-slate-400 font-mono">{org.slug}</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-slate-400 font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" aria-hidden="true" />
            {members.length} member{members.length !== 1 ? 's' : ''}
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-100 rounded-xl p-1">
        {TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex-1 py-2 px-1 text-xs font-bold rounded-lg transition-all flex items-center justify-center gap-1.5 ${
              activeTab === tab.key ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            {tab.label}
            {tab.count !== undefined && tab.count > 0 && (
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
                tab.amber && activeTab !== tab.key
                  ? 'bg-amber-100 text-amber-700'
                  : activeTab === tab.key
                  ? 'bg-slate-100 text-slate-600'
                  : 'bg-slate-200/70 text-slate-500'
              }`}>
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Escalated tab ── */}
      {activeTab === 'escalated' && (
        <EscalatedQueuePanel token={token} onToast={onToast} />
      )}

      {/* ── Members tab ── */}
      {activeTab === 'members' && (
        <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100">
            <h3 className="text-sm font-bold text-slate-900">
              Members
              <span className="text-slate-400 font-normal ml-2 text-xs">({members.length})</span>
            </h3>
          </div>
          {members.length === 0 ? (
            <p className="px-5 py-8 text-sm text-slate-400 text-center">No verified members yet.</p>
          ) : (
            <div className="divide-y divide-slate-100">
              {members.map((m) => {
                const initials = m.first_name && m.last_name
                  ? `${m.first_name[0]}${m.last_name[0]}`.toUpperCase()
                  : m.email.slice(0, 2).toUpperCase()
                const fullName = m.first_name ? `${m.first_name} ${m.last_name ?? ''}`.trim() : null
                return (
                <div key={m.id} className="px-5 py-3.5 flex items-center justify-between hover:bg-slate-50/60 transition-colors">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-9 h-9 rounded-full bg-gradient-to-br from-indigo-400 to-indigo-600 flex items-center justify-center flex-shrink-0 shadow-sm">
                      <span className="text-[11px] font-bold text-white">{initials}</span>
                    </div>
                    <div className="min-w-0">
                      {fullName && <p className="text-sm text-slate-900 font-semibold truncate">{fullName}</p>}
                      <p className={`truncate ${fullName ? 'text-xs text-slate-400' : 'text-sm text-slate-800 font-medium'}`}>{m.email}</p>
                      <p className="text-[11px] text-slate-300 mt-0.5">{relativeTime(m.created_at)}</p>
                    </div>
                  </div>
                  <span className={`text-[11px] font-bold px-2.5 py-1 rounded-full flex-shrink-0 ${
                    m.role === 'admin' ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-600'
                  }`}>
                    {m.role}
                  </span>
                </div>
              )})}
            </div>
          )}
        </div>
      )}

      {/* ── Invites tab ── */}
      {activeTab === 'invites' && (
        <InvitesPanel
          token={token}
          invites={invites}
          onInvitesChange={setInvites}
          onToast={onToast}
        />
      )}

      {/* ── KB tab ── */}
      {activeTab === 'kb' && <KnowledgeBasePanel token={token} onToast={onToast} />}

      {/* ── Tickets tab ── */}
      {activeTab === 'tickets' && (
        <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between gap-3 flex-wrap">
            <h3 className="text-sm font-bold text-slate-900">
              All tickets
              <span className="text-slate-400 font-normal ml-2 text-xs">({ticketTotal})</span>
            </h3>
            <div className="flex gap-0.5 bg-slate-100 rounded-lg p-0.5 overflow-x-auto scrollbar-none">
              {TICKET_FILTERS.map(({ val, label }) => (
                <button
                  key={val}
                  onClick={() => handleStatusFilter(val)}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all whitespace-nowrap ${
                    statusFilter === val ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {tickets.length === 0 ? (
            <div className="px-5 py-10 text-center">
              <p className="text-sm text-slate-400 font-medium">No tickets match this filter.</p>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {tickets.map((t) => {
                const cfg = STATUS_CONFIG[t.status] ?? STATUS_CONFIG.pending
                return (
                  <div key={t.ticket_id} className="px-5 py-4 hover:bg-slate-50/60 transition-colors">
                    <div
                      className="flex items-start justify-between gap-4 cursor-pointer group"
                      onClick={() => setExpandedTicket(expandedTicket === t.ticket_id ? null : t.ticket_id)}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1.5">
                          <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${cfg.dot}`} aria-hidden="true" />
                          <span className="text-[10px] font-mono text-slate-400">#{t.ticket_id.slice(0, 8).toUpperCase()}</span>
                          {t.category && (
                            <>
                              <span className="text-slate-200 text-xs">·</span>
                              <span className="text-[11px] font-semibold text-slate-500">{CATEGORY_LABEL[t.category] ?? t.category}</span>
                            </>
                          )}
                          {t.admin_note && (
                            <span className="text-[10px] font-semibold bg-indigo-50 text-indigo-500 border border-indigo-100 rounded-full px-1.5 py-0.5">note</span>
                          )}
                        </div>
                        <p className="text-sm text-slate-700 truncate pr-4">
                          {t.resolution?.slice(0, 90) ?? t.escalation_reason ?? '—'}
                        </p>
                        <p className="text-xs text-slate-400 mt-1">{relativeTime(t.created_at)}</p>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0 pt-0.5">
                        <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-bold border capitalize ${cfg.badge}`}>
                          {t.status}
                        </span>
                        <svg
                          className={`w-4 h-4 text-slate-300 group-hover:text-slate-500 transition-all duration-150 ${expandedTicket === t.ticket_id ? 'rotate-180 text-slate-500' : ''}`}
                          viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"
                        >
                          <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
                        </svg>
                      </div>
                    </div>

                    {expandedTicket === t.ticket_id && (
                      <ResolvePanel
                        ticket={t}
                        token={token}
                        onToast={onToast}
                        onDone={updated => {
                          handleTicketUpdated(updated as TicketRow)
                          setExpandedTicket(null)
                        }}
                      />
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {/* Pagination */}
          {ticketTotal > LIMIT && (
            <div className="px-5 py-3.5 border-t border-slate-100 flex items-center justify-between">
              <span className="text-xs text-slate-400">
                {ticketOffset + 1}–{Math.min(ticketOffset + LIMIT, ticketTotal)} of {ticketTotal}
              </span>
              <div className="flex gap-2">
                <button
                  disabled={ticketOffset === 0}
                  onClick={() => loadTickets(Math.max(0, ticketOffset - LIMIT), statusFilter)}
                  className="text-xs font-semibold text-slate-600 border border-slate-200 rounded-xl px-3.5 py-1.5 hover:bg-slate-50 disabled:opacity-40 transition-all"
                >
                  ← Previous
                </button>
                <button
                  disabled={ticketOffset + LIMIT >= ticketTotal}
                  onClick={() => loadTickets(ticketOffset + LIMIT, statusFilter)}
                  className="text-xs font-semibold text-slate-600 border border-slate-200 rounded-xl px-3.5 py-1.5 hover:bg-slate-50 disabled:opacity-40 transition-all"
                >
                  Next →
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
