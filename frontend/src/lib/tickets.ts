// Shared ticket vocabulary for every screen that shows tickets, so a status can
// never mean one thing on the New Ticket page and another in My Tickets.

export type TicketStatus =
  | 'pending'
  | 'processing'
  | 'awaiting_confirmation'
  | 'resolved'
  | 'escalated'
  | 'failed'

export interface TicketSummary {
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

interface StatusMeta {
  label: string
  dot: string
  badge: string
  /** True while the agents are still working — the UI keeps refreshing. */
  inProgress?: boolean
  /** True when the user must do something. */
  needsAction?: boolean
}

export const STATUS_META: Record<TicketStatus, StatusMeta> = {
  pending: { label: 'Queued', dot: 'bg-indigo-400 animate-pulse', badge: 'bg-indigo-50 text-indigo-700 border-indigo-200', inProgress: true },
  processing: { label: 'Processing', dot: 'bg-indigo-500 animate-pulse', badge: 'bg-indigo-50 text-indigo-700 border-indigo-200', inProgress: true },
  awaiting_confirmation: { label: 'Needs your confirmation', dot: 'bg-rose-500', badge: 'bg-rose-50 text-rose-700 border-rose-200', needsAction: true },
  resolved: { label: 'Resolved', dot: 'bg-emerald-500', badge: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  escalated: { label: 'With support team', dot: 'bg-amber-500', badge: 'bg-amber-50 text-amber-700 border-amber-200' },
  failed: { label: 'Failed', dot: 'bg-red-500', badge: 'bg-red-50 text-red-700 border-red-200' },
}

const UNKNOWN_STATUS: StatusMeta = { label: 'Unknown', dot: 'bg-slate-400', badge: 'bg-slate-50 text-slate-600 border-slate-200' }

export function statusMeta(status: string): StatusMeta {
  return STATUS_META[status as TicketStatus] ?? UNKNOWN_STATUS
}

export const CATEGORY_LABEL: Record<string, string> = {
  password_reset: 'Password reset',
  access_request: 'Access request',
  software_install: 'Software install',
  incident_report: 'Incident',
  leave_approval: 'Leave',
  access_revoke: 'Remove access',
  account_lock: 'Lock account',
  account_delete: 'Delete account',
  unknown: 'General question',
}

export function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60_000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return d === 1 ? 'yesterday' : `${d}d ago`
}

/** POST confirm-action / cancel. Returns an error message, or null on success. */
export async function decideTicket(
  ticketId: string,
  token: string,
  decision: 'confirm-action' | 'cancel',
): Promise<string | null> {
  try {
    const r = await fetch(`/tickets/${ticketId}/${decision}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    })
    if (r.ok) return null
    const body = await r.json().catch(() => ({}))
    return body?.detail?.error ?? `Request failed (HTTP ${r.status})`
  } catch {
    return 'Network error — please try again.'
  }
}
