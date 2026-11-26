import { useCallback, useEffect, useState } from 'react'
import { CATEGORY_LABEL, relativeTime, statusMeta, type TicketSummary } from '../lib/tickets'

const REFRESH_MS = 5000

/** Alert shown when one or more tickets are waiting for the user's confirmation. */
export function NeedsActionBanner({ token, onReview }: { token: string; onReview: () => void }) {
  const [count, setCount] = useState(0)

  useEffect(() => {
    let cancelled = false
    fetch('/tickets/?status=awaiting_confirmation&limit=1', { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (!cancelled && d) setCount(d.total ?? 0) })
      .catch(() => { /* non-critical */ })
    return () => { cancelled = true }
  }, [token])

  if (count === 0) return null
  return (
    <div role="alert" className="mb-6 flex items-center gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 fade-in">
      <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-rose-100 text-rose-600" aria-hidden="true">
        <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" /></svg>
      </span>
      <p className="flex-1 text-sm text-rose-800">
        <span className="font-semibold">{count} request{count > 1 ? 's' : ''} need{count > 1 ? '' : 's'} your confirmation.</span>{' '}
        Nothing has been changed yet.
      </p>
      <button
        onClick={onReview}
        className="flex-shrink-0 rounded-lg bg-rose-600 px-3.5 py-2 text-xs font-semibold text-white transition-colors hover:bg-rose-700"
      >
        Review
      </button>
    </div>
  )
}

/** The user's five most recent tickets, refreshing live while any are in progress. */
export function RecentTickets({ token, onViewAll }: { token: string; onViewAll: () => void }) {
  const [tickets, setTickets] = useState<TicketSummary[] | null>(null)

  const load = useCallback(async () => {
    try {
      const r = await fetch('/tickets/?limit=5', { headers: { Authorization: `Bearer ${token}` } })
      if (r.ok) setTickets((await r.json()).tickets ?? [])
    } catch { /* keep last known list */ }
  }, [token])

  useEffect(() => { load() }, [load])

  const anyInProgress = (tickets ?? []).some((t) => statusMeta(t.status).inProgress)
  useEffect(() => {
    if (!anyInProgress) return
    const id = setInterval(load, REFRESH_MS)
    return () => clearInterval(id)
  }, [anyInProgress, load])

  return (
    <section className="rounded-2xl border border-slate-200 bg-white shadow-sm" aria-labelledby="recent-heading">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
        <h3 id="recent-heading" className="text-sm font-bold text-slate-900">Your recent tickets</h3>
        {tickets && tickets.length > 0 && (
          <button onClick={onViewAll} className="text-xs font-semibold text-indigo-600 hover:text-indigo-800">
            View all →
          </button>
        )}
      </div>

      {tickets === null ? (
        <div className="space-y-3 px-5 py-4" aria-hidden="true">
          {[0, 1, 2].map((i) => <div key={i} className="h-9 animate-pulse rounded-lg bg-slate-100" />)}
        </div>
      ) : tickets.length === 0 ? (
        <p className="px-5 py-6 text-center text-sm text-slate-400">Your tickets will appear here.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {tickets.map((t) => {
            const meta = statusMeta(t.status)
            const title = t.category && t.category !== 'unknown'
              ? CATEGORY_LABEL[t.category] ?? t.category
              : (t.raw_text ?? 'Request')
            return (
              <li key={t.ticket_id}>
                <button onClick={onViewAll} className="flex w-full items-start gap-3 px-5 py-3 text-left transition-colors hover:bg-slate-50">
                  <span className={`mt-1.5 h-2 w-2 flex-shrink-0 rounded-full ${meta.dot}`} aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-slate-800">{title}</span>
                    <span className={`text-xs ${meta.needsAction ? 'font-semibold text-rose-600' : 'text-slate-400'}`}>
                      {meta.label} · {relativeTime(t.created_at)}
                    </span>
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

const STEPS = [
  {
    title: 'Resolved automatically',
    body: 'Password resets, access requests, leave, outage reports, and questions your organisation’s documents answer — usually within seconds. Software requests go to your manager for approval.',
    tone: 'bg-emerald-100 text-emerald-700',
    icon: 'M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z',
  },
  {
    title: 'You confirm risky changes',
    body: 'Removing access or locking/deleting an account never happens without your explicit OK.',
    tone: 'bg-rose-100 text-rose-700',
    icon: 'M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z',
  },
  {
    title: 'A person takes over when needed',
    body: 'If we’re not sure, your request goes to the right support team with everything we found.',
    tone: 'bg-amber-100 text-amber-700',
    icon: 'M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z',
  },
]

/** Sets expectations: what is automatic, what needs the user, what goes to a person. */
export function HowItWorks() {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm" aria-labelledby="how-heading">
      <h3 id="how-heading" className="mb-3 text-sm font-bold text-slate-900">What happens next</h3>
      <ol className="space-y-3.5">
        {STEPS.map((s) => (
          <li key={s.title} className="flex gap-3">
            <span className={`flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg ${s.tone}`} aria-hidden="true">
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path strokeLinecap="round" strokeLinejoin="round" d={s.icon} />
              </svg>
            </span>
            <span>
              <span className="block text-sm font-semibold text-slate-800">{s.title}</span>
              <span className="block text-xs leading-relaxed text-slate-500">{s.body}</span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
}
