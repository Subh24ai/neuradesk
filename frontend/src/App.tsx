import { useCallback, useEffect, useState } from 'react'
import AdminDashboard from './components/AdminDashboard'
import AgentTimeline from './components/AgentTimeline'
import LoginForm from './components/LoginForm'
import TicketForm from './components/TicketForm'
import TicketHistory from './components/TicketHistory'

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

// ── Password field ────────────────────────────────────────────────────────────

function PasswordField({
  id, label, value, onChange, show, onToggleShow,
  autoComplete, placeholder, minLength, state,
}: {
  id: string; label: string; value: string; onChange: (v: string) => void
  show: boolean; onToggleShow: () => void
  autoComplete?: string; placeholder?: string; minLength?: number
  state?: 'error' | 'success' | 'default'
}) {
  const borderCls =
    state === 'error'   ? 'border-red-300 focus:ring-red-400/30 focus:border-red-400' :
    state === 'success' ? 'border-emerald-300 focus:ring-emerald-400/30 focus:border-emerald-400' :
    'border-slate-200 hover:border-slate-300 focus:ring-indigo-400/30 focus:border-indigo-400'

  return (
    <div>
      <label htmlFor={id} className="block text-[11px] font-semibold text-slate-500 uppercase tracking-widest mb-1.5">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type={show ? 'text' : 'password'}
          required
          autoComplete={autoComplete}
          minLength={minLength}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          aria-invalid={state === 'error'}
          className={`w-full border rounded-xl px-3.5 py-2.5 pr-20 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 transition-all duration-150 bg-slate-50/40 focus:bg-white ${borderCls}`}
        />
        <div className="absolute inset-y-0 right-0 flex items-center gap-0.5 pr-3">
          {state === 'success' && (
            <svg className="w-4 h-4 text-emerald-500 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
            </svg>
          )}
          {state === 'error' && (
            <svg className="w-4 h-4 text-red-400 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
            </svg>
          )}
          <button
            type="button"
            onClick={onToggleShow}
            aria-label={show ? 'Hide password' : 'Show password'}
            className="text-slate-400 hover:text-slate-600 transition-colors p-0.5"
          >
            {show ? (
              <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path d="M3.28 2.22a.75.75 0 00-1.06 1.06l14.5 14.5a.75.75 0 101.06-1.06l-1.745-1.745a10.029 10.029 0 003.3-4.38 1.002 1.002 0 000-.704 10.978 10.978 0 00-7.84-6.77.75.75 0 10-.36 1.455 9.479 9.479 0 016.46 5.667 8.529 8.529 0 01-2.84 3.567L13.95 13.3A4.002 4.002 0 009.75 9.1l-1.424-1.424A6.002 6.002 0 0110 7.5c3.56 0 6.773 2.44 7.963 5.5a9.478 9.478 0 01-2.33 3.43zM10 4.5c.66 0 1.3.08 1.913.231l-1.52-1.52A10.006 10.006 0 0010 3C6.44 3 3.228 5.44 2.037 8.5a9.99 9.99 0 002.542 3.842L5.93 11a4.002 4.002 0 014.887-5.494L9.22 3.907A10.02 10.02 0 0010 4.5zM8.012 9.37a2.5 2.5 0 002.619 2.619L8.012 9.37z" />
              </svg>
            ) : (
              <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path d="M10 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z" />
                <path fillRule="evenodd" d="M.664 10.59a1.651 1.651 0 010-1.186A10.004 10.004 0 0110 3c4.257 0 7.893 2.66 9.336 6.41.147.381.146.804 0 1.186A10.004 10.004 0 0110 17c-4.257 0-7.893-2.66-9.336-6.41zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clipRule="evenodd" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Password strength ─────────────────────────────────────────────────────────

function getStrength(pw: string): 0 | 1 | 2 | 3 | 4 {
  if (!pw) return 0
  let s = 0
  if (pw.length >= 8) s++
  if (pw.length >= 12) s++
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s++
  if (/[0-9]/.test(pw)) s++
  if (/[^A-Za-z0-9]/.test(pw)) s++
  return Math.min(4, s) as 0 | 1 | 2 | 3 | 4
}

// ── Account panel ─────────────────────────────────────────────────────────────

interface ActiveSession {
  jti: string
  created_at: string
  expires_at: string
  is_current: boolean
}

function AccountPanel({
  token, email, firstName, lastName, orgName, role, onToast, onPasswordChanged, onLogout,
}: {
  token: string
  email: string
  firstName: string
  lastName: string
  orgName: string
  role: string
  onToast: (msg: string, v?: ToastVariant) => void
  onPasswordChanged: (newToken: string) => void
  onLogout: () => void
}) {
  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [showCurrentPw, setShowCurrentPw] = useState(false)
  const [showNewPw, setShowNewPw] = useState(false)
  const [showConfirmPw, setShowConfirmPw] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sessions, setSessions] = useState<ActiveSession[]>([])
  const [sessionsLoading, setSessionsLoading] = useState(true)
  const [revokingJti, setRevokingJti] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function loadSessions() {
      try {
        const r = await fetch('/auth/sessions', { headers: { Authorization: `Bearer ${token}` } })
        if (r.ok && !cancelled) {
          const data = await r.json() as { sessions: ActiveSession[] }
          setSessions(data.sessions)
        }
      } catch { /* non-critical */ } finally {
        if (!cancelled) setSessionsLoading(false)
      }
    }
    loadSessions()
    return () => { cancelled = true }
  }, [token])

  const initials = firstName
    ? firstName.charAt(0).toUpperCase() + (lastName ? lastName.charAt(0).toUpperCase() : '')
    : email.charAt(0).toUpperCase()

  const strength = getStrength(newPw)
  const strengthMeta = [
    { label: '',       bar: '',              text: '' },
    { label: 'Weak',   bar: 'bg-red-400',    text: 'text-red-500' },
    { label: 'Fair',   bar: 'bg-amber-400',  text: 'text-amber-500' },
    { label: 'Good',   bar: 'bg-blue-400',   text: 'text-blue-500' },
    { label: 'Strong', bar: 'bg-emerald-400', text: 'text-emerald-500' },
  ][strength]

  const newPwState: 'error' | 'success' | 'default' =
    newPw.length === 0 ? 'default' : newPw.length < 8 ? 'error' : 'success'
  const confirmPwState: 'error' | 'success' | 'default' =
    confirmPw.length === 0 ? 'default' : confirmPw === newPw ? 'success' : 'error'

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (newPw.length < 8) { setError('New password must be at least 8 characters.'); return }
    if (newPw !== confirmPw) { setError('Passwords do not match.'); return }
    setSaving(true)
    try {
      const res = await fetch('/auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ current_password: currentPw, new_password: newPw }),
      })
      const data = await res.json() as { access_token?: string; detail?: { error?: string } | string }
      if (!res.ok) {
        const detail = data.detail
        setError(typeof detail === 'string' ? detail : (detail?.error ?? 'Failed to change password'))
        return
      }
      setCurrentPw(''); setNewPw(''); setConfirmPw('')
      onToast('Password changed successfully', 'success')
      if (data.access_token) onPasswordChanged(data.access_token)
    } catch {
      setError('Network error')
    } finally {
      setSaving(false)
    }
  }

  async function handleRevoke(jti: string) {
    setRevokingJti(jti)
    try {
      const r = await fetch(`/auth/sessions/${jti}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (r.ok || r.status === 204) {
        setSessions(prev => prev.filter(s => s.jti !== jti))
        onToast('Session revoked', 'success')
      } else {
        onToast('Failed to revoke session', 'error')
      }
    } catch {
      onToast('Network error', 'error')
    } finally {
      setRevokingJti(null)
    }
  }

  return (
    <div className="fade-in space-y-5 max-w-lg">
      <div>
        <h2 className="text-2xl font-bold text-slate-900 tracking-tight font-display">Account settings</h2>
        <p className="mt-1 text-sm text-slate-500">Manage your profile, security, and sessions.</p>
      </div>

      {/* Profile card — frosted glass */}
      <div className="relative bg-white/70 backdrop-blur-xl rounded-2xl border border-slate-200/60 overflow-hidden shadow-sm">
        <div className="h-20 bg-gradient-to-r from-indigo-500 via-indigo-600 to-violet-600 relative overflow-hidden">
          <div
            className="absolute inset-0 opacity-[0.15]"
            style={{ backgroundImage: 'radial-gradient(circle, white 1px, transparent 1px)', backgroundSize: '20px 20px' }}
            aria-hidden="true"
          />
        </div>
        <div className="px-5 pb-5">
          <div className="flex items-end justify-between -mt-8 mb-4">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-400 to-violet-600 flex items-center justify-center shadow-lg ring-4 ring-white flex-shrink-0">
              <span className="text-xl font-extrabold text-white">{initials}</span>
            </div>
            <span className={`text-xs font-bold px-3 py-1 rounded-full mb-2 capitalize ${role === 'admin' ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-600'}`}>
              {role}
            </span>
          </div>
          {firstName ? (
            <p className="text-lg font-bold text-slate-900 font-display">{firstName} {lastName}</p>
          ) : null}
          <p className={`text-sm truncate ${firstName ? 'text-slate-500' : 'text-lg font-bold text-slate-900'}`}>{email}</p>
          {orgName && (
            <p className="text-xs text-slate-400 mt-1.5 flex items-center gap-1.5">
              <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M4 16.5v-13h-.25a.75.75 0 010-1.5h12.5a.75.75 0 010 1.5H16v13h.25a.75.75 0 010 1.5h-3.5a.75.75 0 01-.75-.75v-2.5a.75.75 0 00-.75-.75h-2.5a.75.75 0 00-.75.75v2.5a.75.75 0 01-.75.75h-3.5a.75.75 0 010-1.5H4zm3-11a.75.75 0 01.75-.75h.5a.75.75 0 010 1.5h-.5A.75.75 0 017 5.5zm.75 2.25a.75.75 0 000 1.5h.5a.75.75 0 000-1.5h-.5zm-.75 4a.75.75 0 01.75-.75h.5a.75.75 0 010 1.5h-.5a.75.75 0 01-.75-.75zm5.25-6a.75.75 0 000 1.5h.5a.75.75 0 000-1.5h-.5zm-.75 4a.75.75 0 01.75-.75h.5a.75.75 0 010 1.5h-.5a.75.75 0 01-.75-.75z" clipRule="evenodd" />
              </svg>
              {orgName}
            </p>
          )}
        </div>
      </div>

      {/* Change password */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
        <div className="px-5 py-4 border-b border-slate-100">
          <h3 className="text-sm font-bold text-slate-900 font-display">Change password</h3>
          <p className="text-xs text-slate-400 mt-0.5">Choose a strong password of at least 8 characters.</p>
        </div>
        <form onSubmit={handleSubmit} className="px-5 py-4 space-y-4">
          <PasswordField
            id="cur-pw"
            label="Current password"
            value={currentPw}
            onChange={setCurrentPw}
            show={showCurrentPw}
            onToggleShow={() => setShowCurrentPw(v => !v)}
            autoComplete="current-password"
            placeholder="••••••••"
          />

          <div className="space-y-1.5">
            <PasswordField
              id="new-pw"
              label="New password"
              value={newPw}
              onChange={setNewPw}
              show={showNewPw}
              onToggleShow={() => setShowNewPw(v => !v)}
              autoComplete="new-password"
              placeholder="Min 8 characters"
              minLength={8}
              state={newPwState}
            />
            {newPw.length > 0 && (
              <div>
                <div className="flex gap-1 mt-2">
                  {[1, 2, 3, 4].map((lvl) => (
                    <div
                      key={lvl}
                      className={`h-1 flex-1 rounded-full transition-all duration-300 ${lvl <= strength ? strengthMeta.bar : 'bg-slate-100'}`}
                    />
                  ))}
                </div>
                <p className={`text-[11px] font-semibold mt-1 ${strengthMeta.text}`}>{strengthMeta.label}</p>
              </div>
            )}
          </div>

          <PasswordField
            id="conf-pw"
            label="Confirm new password"
            value={confirmPw}
            onChange={setConfirmPw}
            show={showConfirmPw}
            onToggleShow={() => setShowConfirmPw(v => !v)}
            autoComplete="new-password"
            placeholder="Repeat your new password"
            state={confirmPwState}
          />

          {error && (
            <div role="alert" className="flex items-center gap-2 text-sm text-red-700 bg-red-50 border border-red-100 rounded-xl px-3.5 py-2.5">
              <svg className="w-4 h-4 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
              </svg>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={saving || !currentPw || !newPw || !confirmPw}
            className="w-full bg-indigo-600 hover:bg-indigo-700 active:scale-[.99] text-white rounded-xl py-2.5 text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-sm"
          >
            {saving ? 'Saving…' : 'Update password'}
          </button>
        </form>
      </div>

      {/* Active sessions */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-900 font-display">Active sessions</h3>
            <p className="text-xs text-slate-400 mt-0.5">All signed-in sessions for your account.</p>
          </div>
          <span className="text-xs font-semibold text-slate-400 bg-slate-100 rounded-full px-2.5 py-1">
            {sessionsLoading ? '…' : sessions.length}
          </span>
        </div>
        {sessionsLoading ? (
          <p className="px-5 py-5 text-sm text-slate-400 text-center">Loading…</p>
        ) : sessions.length === 0 ? (
          <p className="px-5 py-5 text-sm text-slate-400 text-center">No active sessions</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {sessions.map((session) => (
              <li key={session.jti} className="px-5 py-3.5 flex items-start gap-3.5">
                <div className="w-9 h-9 rounded-xl bg-slate-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <svg className="w-5 h-5 text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25m18 0A2.25 2.25 0 0018.75 3H5.25A2.25 2.25 0 003 5.25m18 0H3" />
                  </svg>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-semibold text-slate-800 font-mono text-xs">{session.jti.slice(0, 8)}…</p>
                    {session.is_current && (
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-100 rounded-full px-2 py-0.5">
                        <span className="w-1 h-1 rounded-full bg-emerald-500 animate-pulse" aria-hidden="true" />
                        Current
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Created {new Date(session.created_at).toLocaleString()}
                  </p>
                  <p className="text-xs text-slate-400">
                    Expires {new Date(session.expires_at).toLocaleString()}
                  </p>
                </div>
                {!session.is_current && (
                  <button
                    onClick={() => handleRevoke(session.jti)}
                    disabled={revokingJti === session.jti}
                    className="flex-shrink-0 text-xs font-semibold text-red-500 hover:text-red-700 border border-red-100 hover:border-red-200 hover:bg-red-50 rounded-lg px-2.5 py-1.5 transition-all mt-0.5 active:scale-95 disabled:opacity-40"
                  >
                    {revokingJti === session.jti ? '…' : 'Revoke'}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Sign out */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
        <div className="px-5 py-4 flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-slate-700">Sign out of NeuraDesk</p>
            <p className="text-xs text-slate-400 mt-0.5">You'll need to sign in again to access your account.</p>
          </div>
          <button
            onClick={onLogout}
            className="flex-shrink-0 text-sm font-semibold text-red-600 hover:text-red-800 border border-red-200 hover:border-red-300 rounded-xl px-4 py-2 hover:bg-red-50 active:scale-[.98] transition-all"
          >
            Sign out
          </button>
        </div>
      </div>
    </div>
  )
}

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
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isCreating, setIsCreating] = useState(false)
  const [prefillText, setPrefillText] = useState('')
  const [toasts, setToasts] = useState<Toast[]>([])
  const [agentsOnline, setAgentsOnline] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function checkHealth() {
      try {
        const r = await fetch('/health')
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
        const updated: Auth = { ...state, firstName: profile.first_name, lastName: profile.last_name, orgName: profile.org_name }
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

  if (!auth) return <LoginForm onLogin={handleLogin} />

  const initials = auth.email.charAt(0).toUpperCase()
  const isProcessing = submission !== null

  const greeting = (() => {
    const h = new Date().getHours()
    const g = h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
    return auth.firstName ? `${g}, ${auth.firstName}` : g
  })()

  function navTo(view: AppView) {
    setSubmission(null)
    setSubmitError(null)
    setAppView(view)
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
          <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-7 lg:py-8 pb-28 lg:pb-10">
            {isProcessing ? (
              <AgentTimeline
                ticketId={submission.ticketId}
                text={submission.text}
                imageB64={submission.imageB64}
                token={auth.token}
                onReset={() => setSubmission(null)}
              />
            ) : appView === 'admin' ? (
              <AdminDashboard token={auth.token} onNewTicket={() => navTo('form')} onToast={addToast} />
            ) : appView === 'history' ? (
              <TicketHistory token={auth.token} onNewTicket={() => navTo('form')} onRetry={handleRetry} />
            ) : appView === 'account' ? (
              <AccountPanel
                token={auth.token}
                email={auth.email}
                firstName={auth.firstName}
                lastName={auth.lastName}
                orgName={auth.orgName}
                role={auth.role}
                onToast={addToast}
                onPasswordChanged={(newToken) => handleLogin(newToken)}
                onLogout={handleLogout}
              />
            ) : (
              <>
                <TicketForm
                  onSubmit={(text, img) => { setPrefillText(''); handleSubmit(text, img) }}
                  isSubmitting={isCreating}
                  initialText={prefillText}
                  greeting={greeting}
                  agentsOnline={agentsOnline}
                />
                {submitError && (
                  <p className="mt-3 text-sm text-red-600 text-center">{submitError}</p>
                )}
              </>
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
