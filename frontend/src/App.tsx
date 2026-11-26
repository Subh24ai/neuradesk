import { useCallback, useEffect, useState } from 'react'
import AccountSettings from './components/AccountSettings'
import AdminDashboard from './components/AdminDashboard'
import AgentTimeline from './components/AgentTimeline'
import LoginForm from './components/LoginForm'
import { HowItWorks, NeedsActionBanner, RecentTickets } from './components/HomePanels'
import TicketForm from './components/TicketForm'
import TicketHistory, { type HistoryFilter } from './components/TicketHistory'
import { SESSION_ENDED_EVENT, type SessionEndReason } from './lib/session'

interface Auth {
  token: string
  userId: string
  email: string
  orgName: string
  role: string
  firstName: string
  lastName: string
}

function isTokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return typeof payload.exp === 'number' && payload.exp * 1000 < Date.now()
  } catch {
    return true
  }
}

interface Submission {
  ticketId: string
  text: string
  imageB64: string | null
}

interface TicketCreateResponse {
  ticket_id: string
}

type AppView = 'form' | 'history' | 'admin' | 'account'

function decodeJwtPayload(token: string): { sub: string; email: string; org_name: string; role: string; first_name: string; last_name: string } {
  const payload = JSON.parse(atob(token.split('.')[1]))
  return {
    sub: payload.sub as string,
    email: payload.email as string,
    org_name: (payload.org_name as string) || '',
    role: (payload.role as string) || 'member',
    first_name: (payload.first_name as string) || '',
    last_name: (payload.last_name as string) || '',
  }
}

// ── Toast system ──────────────────────────────────────────────────────────────

type ToastVariant = 'success' | 'error' | 'info'

interface Toast {
  id: number
  message: string
  variant: ToastVariant
  exiting?: boolean
}

let _toastId = 0

function ToastContainer({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  if (!toasts.length) return null
  const icons: Record<ToastVariant, string> = {
    success: 'M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z',
    error:   'M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z',
    info:    'M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z',
  }
  const colors: Record<ToastVariant, string> = {
    success: 'bg-emerald-600',
    error:   'bg-red-600',
    info:    'bg-indigo-600',
  }
  return (
    <div className="fixed bottom-20 lg:bottom-5 right-5 z-50 flex flex-col gap-2 pointer-events-none" aria-live="polite">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`flex items-center gap-3 ${colors[t.variant]} text-white text-sm font-medium px-4 py-3 rounded-xl shadow-lg pointer-events-auto max-w-xs ${t.exiting ? 'toast-out' : 'toast-in'}`}
        >
          <svg className="w-4 h-4 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d={icons[t.variant]} clipRule="evenodd" />
          </svg>
          <span className="flex-1">{t.message}</span>
          <button onClick={() => onDismiss(t.id)} className="opacity-70 hover:opacity-100 transition-opacity ml-1" aria-label="Dismiss">
            <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
            </svg>
          </button>
        </div>
      ))}
    </div>
  )
}

// ── Nav config ────────────────────────────────────────────────────────────────

interface NavItem {
  key: AppView
  label: string
  shortLabel: string
  icon: string
  adminOnly?: boolean
}

const NAV_ITEMS: NavItem[] = [
  {
    key: 'form',
    label: 'New Ticket',
    shortLabel: 'New',
    icon: 'M12 9v6m3-3H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z',
  },
  {
    key: 'history',
    label: 'My Tickets',
    shortLabel: 'Tickets',
    icon: 'M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z',
  },
  {
    key: 'admin',
    label: 'Admin',
    shortLabel: 'Admin',
    icon: 'M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z',
    adminOnly: true,
  },
  {
    key: 'account',
    label: 'Account',
    shortLabel: 'Account',
    icon: 'M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z',
  },
]

// ── Main app ──────────────────────────────────────────────────────────────────

export default function App() {
  const [auth, setAuth] = useState<Auth | null>(() => {
    const stored = localStorage.getItem('nd_auth')
    if (!stored) return null
    const parsed = JSON.parse(stored) as Auth
    if (isTokenExpired(parsed.token)) { localStorage.removeItem('nd_auth'); return null }
    return parsed
  })
  const [submission, setSubmission] = useState<Submission | null>(null)
  const [appView, setAppView] = useState<AppView>('form')
  const [historyFilter, setHistoryFilter] = useState<HistoryFilter>('all')
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isCreating, setIsCreating] = useState(false)
  const [prefillText, setPrefillText] = useState('')
  const [toasts, setToasts] = useState<Toast[]>([])
  const [agentsOnline, setAgentsOnline] = useState(true)
  const [sessionNotice, setSessionNotice] = useState<string | null>(null)

  // The server is the source of truth for role and name — the token is a
  // snapshot from sign-in. Re-sync on load, on tab focus and every 2 minutes so
  // a promotion/demotion by an admin shows up without signing out and in.
  useEffect(() => {
    if (!auth?.token) return
    const token = auth.token
    let cancelled = false
    async function sync() {
      try {
        const r = await fetch('/auth/me', { headers: { Authorization: `Bearer ${token}` } })
        if (!r.ok || cancelled) return
        const p = await r.json() as { first_name: string; last_name: string; role: string; org_name: string }
        setAuth((prev) => {
          if (!prev || prev.token !== token) return prev
          if (prev.role === p.role && prev.firstName === p.first_name && prev.lastName === p.last_name && prev.orgName === p.org_name) return prev
          const next = { ...prev, role: p.role, firstName: p.first_name, lastName: p.last_name, orgName: p.org_name }
          try { localStorage.setItem('nd_auth', JSON.stringify(next)) } catch { /* storage unavailable */ }
          return next
        })
      } catch { /* offline — keep current */ }
    }
    sync()
    const id = setInterval(sync, 120_000)
    window.addEventListener('focus', sync)
    return () => { cancelled = true; clearInterval(id); window.removeEventListener('focus', sync) }
  }, [auth?.token])

  // Any API call that finds the session dead signs the user out with a reason.
  useEffect(() => {
    function onEnded(e: Event) {
      const reason = (e as CustomEvent<SessionEndReason>).detail
      setSessionNotice(reason === 'deactivated'
        ? 'Your account has been deactivated. Contact your administrator.'
        : 'Your session has ended. Please sign in again.')
      try { localStorage.removeItem('nd_auth') } catch { /* storage unavailable */ }
      setAuth(null)
      setSubmission(null)
      setAppView('form')
    }
    window.addEventListener(SESSION_ENDED_EVENT, onEnded)
    return () => window.removeEventListener(SESSION_ENDED_EVENT, onEnded)
  }, [])

  useEffect(() => {
    let cancelled = false
    async function checkHealth() {
      try {
        // /health/deep verifies DB + RAG index + LLM provider config, so the
        // "agents online" badge reflects real readiness, not just process liveness.
        const r = await fetch('/health/deep')
        if (!cancelled) setAgentsOnline(r.ok)
      } catch {
        if (!cancelled) setAgentsOnline(false)
      }
    }
    checkHealth()
    const id = setInterval(checkHealth, 60_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  const addToast = useCallback((message: string, variant: ToastVariant = 'info') => {
    const id = ++_toastId
    setToasts((prev) => [...prev, { id, message, variant }])
    setTimeout(() => {
      setToasts((prev) => prev.map((t) => t.id === id ? { ...t, exiting: true } : t))
      setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 240)
    }, 3500)
  }, [])

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.map((t) => t.id === id ? { ...t, exiting: true } : t))
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 240)
  }, [])

  async function handleLogin(token: string) {
    const { sub: userId, email, org_name: orgName, role, first_name: firstName, last_name: lastName } = decodeJwtPayload(token)
    const state: Auth = { token, userId, email, orgName, role, firstName, lastName }
    localStorage.setItem('nd_auth', JSON.stringify(state))
    setAuth(state)
    // Fetch real profile — JWT may have empty first_name for older accounts
    try {
      const res = await fetch('/auth/me', { headers: { Authorization: `Bearer ${token}` } })
      if (res.ok) {
        const profile = await res.json() as { first_name: string; last_name: string; email: string; role: string; org_name: string }
        const updated: Auth = { ...state, firstName: profile.first_name, lastName: profile.last_name, orgName: profile.org_name, role: profile.role }
        localStorage.setItem('nd_auth', JSON.stringify(updated))
        setAuth(updated)
      }
    } catch { /* non-critical — JWT fields remain */ }
  }

  useEffect(() => {
    if (!auth) return
    const interval = setInterval(async () => {
      try {
        const payload = JSON.parse(atob(auth.token.split('.')[1]))
        const minsLeft = (payload.exp * 1000 - Date.now()) / 60_000
        if (minsLeft < 30) {
          const res = await fetch('/auth/refresh', { method: 'POST', headers: { Authorization: `Bearer ${auth.token}` } })
          if (res.ok) { const { access_token } = await res.json(); handleLogin(access_token) }
          else handleLogout()
        }
      } catch { /* ignore */ }
    }, 5 * 60 * 1000)
    return () => clearInterval(interval)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth?.token])

  function handleLogout() {
    // Revoke the token on the server too — clearing the browser alone would leave
    // it valid (and listed as an active session) until it expires.
    if (auth?.token) {
      fetch('/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${auth.token}` } }).catch(() => {})
    }
    localStorage.removeItem('nd_auth')
    setAuth(null)
    setSubmission(null)
    setAppView('form')
  }

  async function handleSubmit(text: string, imageB64: string | null) {
    setSubmitError(null)
    setIsCreating(true)
    try {
      const res = await fetch('/tickets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth!.token}` },
        body: JSON.stringify({ text, image_b64: imageB64 }),
      })
      if (res.status === 401) { handleLogout(); return }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body?.detail?.error ?? `HTTP ${res.status}`)
      }
      const data = (await res.json()) as TicketCreateResponse
      setSubmission({ ticketId: data.ticket_id, text, imageB64 })
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to create ticket'
      setSubmitError(msg)
      addToast(msg, 'error')
    } finally {
      setIsCreating(false)
    }
  }

  if (!auth) return <LoginForm key={sessionNotice ?? 'login'} onLogin={(t) => { setSessionNotice(null); handleLogin(t) }} notice={sessionNotice} />

  const initials = (auth.firstName || auth.email).charAt(0).toUpperCase()
  const isProcessing = submission !== null

  const greeting = (() => {
    const h = new Date().getHours()
    const g = h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
    return auth.firstName ? `${g}, ${auth.firstName}` : g
  })()

  function navTo(view: AppView) {
    setSubmission(null)
    setSubmitError(null)
    setHistoryFilter('all')
    setAppView(view)
  }

  function openHistory(filter: HistoryFilter) {
    setSubmission(null)
    setSubmitError(null)
    setHistoryFilter(filter)
    setAppView('history')
  }

  function handleRetry(text: string) {
    setPrefillText(text)
    setSubmission(null)
    setSubmitError(null)
    setAppView('form')
  }

  const visibleNav = NAV_ITEMS.filter((item) => !item.adminOnly || auth.role === 'admin')

  function NavIcon({ d, active }: { d: string; active: boolean }) {
    return (
      <svg className="w-5 h-5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={active ? '2' : '1.75'} aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d={d} />
      </svg>
    )
  }

  return (
    <div className="min-h-screen flex bg-slate-50/80">

      {/* ── Desktop sidebar ───────────────────────────────────────────────────── */}
      <aside className="hidden lg:flex flex-col w-56 xl:w-64 shrink-0 bg-slate-900 sticky top-0 h-screen z-10">
        {/* Logo + org */}
        <div className="px-4 py-5 border-b border-white/5">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-sm flex-shrink-0">
              <svg viewBox="0 0 20 20" className="w-5 h-5 text-white" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="min-w-0">
              <p className="text-sm font-bold text-white tracking-tight leading-tight">NeuraDesk</p>
              {auth.orgName && (
                <p className="text-[11px] text-slate-500 truncate leading-tight mt-0.5">{auth.orgName}</p>
              )}
            </div>
          </div>
        </div>

        {/* Nav links */}
        <nav className="flex-1 px-2.5 py-3 space-y-0.5 overflow-y-auto" aria-label="Main navigation">
          {visibleNav.map(({ key, label, icon }) => {
            const active = !isProcessing && appView === key
            return (
              <button
                key={key}
                onClick={() => navTo(key)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 ${
                  active
                    ? 'bg-indigo-600 text-white font-semibold shadow-sm'
                    : 'text-slate-400 hover:bg-white/5 hover:text-white'
                }`}
              >
                <NavIcon d={icon} active={active} />
                <span>{label}</span>
              </button>
            )
          })}
        </nav>

        {/* System status */}
        <div className="px-4 py-3 border-t border-white/5">
          <div className="flex items-center gap-2 mb-3">
            <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${agentsOnline ? 'bg-emerald-400 animate-pulse' : 'bg-red-400'}`} aria-hidden="true" />
            <span className="text-[11px] text-slate-500 font-medium">
              {agentsOnline ? '4 AI agents online' : 'backend offline'}
            </span>
          </div>
          <button
            onClick={() => navTo('account')}
            className="w-full flex items-center gap-3 px-2 py-2 rounded-xl hover:bg-white/5 transition-all group mb-1"
            aria-label="Account settings"
          >
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-400 to-indigo-600 flex items-center justify-center shrink-0 shadow-sm">
              <span className="text-xs font-bold text-white">{initials}</span>
            </div>
            <div className="min-w-0 flex-1 text-left">
              {auth.firstName ? (
                <>
                  <p className="text-xs font-semibold text-slate-200 truncate leading-snug">{auth.firstName} {auth.lastName}</p>
                  <p className="text-[10px] text-slate-500 truncate leading-snug">{auth.email}</p>
                </>
              ) : (
                <>
                  <p className="text-xs font-semibold text-slate-200 truncate leading-snug">{auth.email}</p>
                  <p className="text-[10px] text-slate-500 capitalize leading-snug">{auth.role}</p>
                </>
              )}
            </div>
          </button>
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-xl text-sm text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-all font-medium"
          >
            <svg className="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
            </svg>
            Sign out
          </button>
        </div>
      </aside>

      {/* ── Content area ─────────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-h-screen overflow-hidden">

        {/* Mobile header (hidden on lg+) */}
        <header className="lg:hidden bg-slate-900 sticky top-0 z-10 px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center flex-shrink-0">
              <svg viewBox="0 0 20 20" className="w-4 h-4 text-white" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clipRule="evenodd" />
              </svg>
            </div>
            <span className="font-bold text-sm tracking-tight text-white">NeuraDesk</span>
            {isProcessing && (
              <span className="inline-flex items-center gap-1.5 bg-white/10 text-white text-[10px] font-bold px-2 py-1 rounded-full">
                <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" aria-hidden="true" />
                Processing
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {auth.role === 'admin' && (
              <span className="text-[10px] bg-indigo-600 text-white rounded-full px-2 py-0.5 font-bold">Admin</span>
            )}
            <button
              onClick={() => navTo('account')}
              className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-400 to-indigo-600 flex items-center justify-center shadow-sm"
              aria-label="Account settings"
            >
              <span className="text-xs font-bold text-white">{initials}</span>
            </button>
          </div>
        </header>

        {/* Scrollable main content */}
        <main className="flex-1 overflow-y-auto">
          <div className={`${isProcessing ? 'max-w-2xl' : appView === 'form' ? 'max-w-6xl' : appView === 'history' ? 'max-w-4xl' : appView === 'admin' ? 'max-w-5xl' : appView === 'account' ? 'max-w-4xl' : 'max-w-2xl'} mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-7 lg:py-8 pb-28 lg:pb-10`}>
            {isProcessing ? (
              <AgentTimeline
                ticketId={submission.ticketId}
                text={submission.text}
                imageB64={submission.imageB64}
                token={auth.token}
                onReset={() => setSubmission(null)}
              />
            ) : appView === 'admin' && auth.role === 'admin' ? (
              <AdminDashboard token={auth.token} currentUserId={auth.userId} onNewTicket={() => navTo('form')} onToast={addToast} />
            ) : appView === 'history' ? (
              <TicketHistory
                key={historyFilter}
                token={auth.token}
                onNewTicket={() => navTo('form')}
                onRetry={handleRetry}
                onToast={addToast}
                initialFilter={historyFilter}
              />
            ) : appView === 'account' ? (
              <AccountSettings
                token={auth.token}
                email={auth.email}
                firstName={auth.firstName}
                lastName={auth.lastName}
                orgName={auth.orgName}
                role={auth.role}
                onToast={addToast}
                onPasswordChanged={(newToken) => handleLogin(newToken)}
                onProfileUpdated={(firstName, lastName) => {
                  const updated = { ...auth, firstName, lastName }
                  try { localStorage.setItem('nd_auth', JSON.stringify(updated)) } catch { /* storage unavailable */ }
                  setAuth(updated)
                }}
                onLogout={handleLogout}
              />
            ) : (
              <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_300px] xl:grid-cols-[minmax(0,1fr)_340px]">
                <div className="min-w-0">
                  <NeedsActionBanner token={auth.token} onReview={() => openHistory('action')} />
                  <TicketForm
                    onSubmit={(text, img) => { setPrefillText(''); handleSubmit(text, img) }}
                    isSubmitting={isCreating}
                    initialText={prefillText}
                    greeting={greeting}
                    agentsOnline={agentsOnline}
                  />
                  {submitError && (
                    <p role="alert" className="mt-3 text-sm text-red-600">{submitError}</p>
                  )}
                </div>
                <aside className="space-y-5 lg:pt-1" aria-label="Your tickets and how requests are handled">
                  <RecentTickets token={auth.token} onViewAll={() => openHistory('all')} />
                  <HowItWorks />
                </aside>
              </div>
            )}
          </div>
        </main>

        {/* Mobile bottom tab bar (hidden on lg+) */}
        <nav
          className="lg:hidden fixed bottom-0 inset-x-0 bg-slate-900 border-t border-white/5 z-20 flex pb-safe"
          aria-label="Main navigation"
        >
          {visibleNav.map(({ key, shortLabel, icon }) => {
            const active = !isProcessing && appView === key
            return (
              <button
                key={key}
                onClick={() => navTo(key)}
                className={`flex-1 flex flex-col items-center gap-1 py-3 text-[10px] font-bold transition-colors ${
                  active ? 'text-indigo-400' : 'text-slate-500'
                }`}
              >
                <NavIcon d={icon} active={active} />
                <span>{shortLabel}</span>
              </button>
            )
          })}
        </nav>
      </div>

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  )
}
