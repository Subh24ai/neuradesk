import { useCallback, useEffect, useState } from 'react'

type ToastVariant = 'success' | 'error' | 'info'

interface Props {
  token: string
  email: string
  firstName: string
  lastName: string
  orgName: string
  role: string
  onToast: (msg: string, v?: ToastVariant) => void
  onPasswordChanged: (newToken: string) => void
  onProfileUpdated: (firstName: string, lastName: string) => void
  onLogout: () => void
}

interface ActiveSession {
  jti: string
  created_at: string
  expires_at: string
  is_current: boolean
  user_agent: string | null
  ip_address: string | null
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/** "Chrome on macOS" from a User-Agent string (display only). */
export function describeDevice(ua: string | null): { label: string; mobile: boolean } {
  if (!ua) return { label: 'Unknown device', mobile: false }
  const browser =
    /Edg\//.test(ua) ? 'Edge'
    : /OPR\//.test(ua) ? 'Opera'
    : /Firefox\//.test(ua) ? 'Firefox'
    : /Chrome\//.test(ua) ? 'Chrome'
    : /Safari\//.test(ua) ? 'Safari'
    : null
  const os =
    /iPhone/.test(ua) ? 'iPhone'
    : /iPad/.test(ua) ? 'iPad'
    : /Android/.test(ua) ? 'Android'
    : /Mac OS X|Macintosh/.test(ua) ? 'macOS'
    : /Windows/.test(ua) ? 'Windows'
    : /Linux/.test(ua) ? 'Linux'
    : null
  const mobile = /iPhone|Android|Mobile/.test(ua)
  if (browser && os) return { label: `${browser} on ${os}`, mobile }
  return { label: browser ?? os ?? 'Unknown device', mobile }
}

function ago(iso: string): string {
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60_000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m} min ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h} h ago`
  return `${Math.round(h / 24)} d ago`
}

function inFuture(iso: string): string {
  const m = Math.round((new Date(iso).getTime() - Date.now()) / 60_000)
  if (m < 60) return `${Math.max(m, 1)} min`
  const h = Math.round(m / 60)
  return h < 24 ? `${h} h` : `${Math.round(h / 24)} d`
}

function strengthOf(pw: string): 0 | 1 | 2 | 3 | 4 {
  if (!pw) return 0
  let s = 0
  if (pw.length >= 8) s++
  if (pw.length >= 12) s++
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s++
  if (/[0-9]/.test(pw)) s++
  if (/[^A-Za-z0-9]/.test(pw)) s++
  return Math.min(4, s) as 0 | 1 | 2 | 3 | 4
}

function Svg({ d, className = 'h-4 w-4' }: { d: string; className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d={d} />
    </svg>
  )
}

const ICON = {
  desktop: 'M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25m18 0A2.25 2.25 0 0018.75 3H5.25A2.25 2.25 0 003 5.25m18 0H3',
  phone: 'M10.5 1.5H8.25A2.25 2.25 0 006 3.75v16.5a2.25 2.25 0 002.25 2.25h7.5A2.25 2.25 0 0018 20.25V3.75a2.25 2.25 0 00-2.25-2.25H13.5m-3 0V3h3V1.5m-3 0h3m-3 18.75h3',
  check: 'M4.5 12.75l6 6 9-13.5',
  dot: 'M12 12h.01',
  eye: 'M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z M15 12a3 3 0 11-6 0 3 3 0 016 0z',
  eyeOff: 'M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88',
  lock: 'M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z',
}

/** A settings row: title + description on the left, content on the right. */
function Section({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-4 border-t border-slate-200 py-7 first:border-t-0 first:pt-0 md:grid-cols-[220px_minmax(0,1fr)] md:gap-10">
      <div>
        <h3 className="text-sm font-bold text-slate-900">{title}</h3>
        <p className="mt-1 text-xs leading-relaxed text-slate-500">{description}</p>
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  )
}

const inputCls = 'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100'

function PasswordInput({ id, label, value, onChange, autoComplete }: {
  id: string; label: string; value: string; onChange: (v: string) => void; autoComplete: string
}) {
  const [show, setShow] = useState(false)
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-xs font-semibold text-slate-700">{label}</label>
      <div className="relative">
        <input id={id} type={show ? 'text' : 'password'} value={value} autoComplete={autoComplete}
          onChange={(e) => onChange(e.target.value)} className={`${inputCls} pr-10`} />
        <button type="button" onClick={() => setShow((v) => !v)} aria-label={show ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
          className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-slate-400 hover:text-slate-600">
          <Svg d={show ? ICON.eyeOff : ICON.eye} />
        </button>
      </div>
    </div>
  )
}

// ── Sections ─────────────────────────────────────────────────────────────────

function ProfileSection({ token, email, firstName, lastName, orgName, role, onToast, onProfileUpdated }: Pick<Props,
  'token' | 'email' | 'firstName' | 'lastName' | 'orgName' | 'role' | 'onToast' | 'onProfileUpdated'>) {
  const [editing, setEditing] = useState(false)
  const [first, setFirst] = useState(firstName)
  const [last, setLast] = useState(lastName)
  const [saving, setSaving] = useState(false)
  const initials = ((firstName || email)[0] + (lastName?.[0] ?? '')).toUpperCase()
  const canSave = first.trim() && last.trim() && (first.trim() !== firstName || last.trim() !== lastName)

  async function save(e: React.FormEvent) {
    e.preventDefault()
    if (!canSave) return
    setSaving(true)
    try {
      const r = await fetch('/auth/me', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ first_name: first.trim(), last_name: last.trim() }),
      })
      if (!r.ok) throw new Error()
      const d = await r.json()
      onProfileUpdated(d.first_name, d.last_name)
      onToast('Name updated', 'success')
      setEditing(false)
    } catch {
      onToast('Could not update your name — please try again.', 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start gap-4">
        <span className="flex h-14 w-14 flex-shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 text-lg font-extrabold text-white shadow-sm" aria-hidden="true">
          {initials}
        </span>
        <div className="min-w-0 flex-1">
          {editing ? (
            <form onSubmit={save} className="space-y-3">
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <label htmlFor="first-name" className="mb-1.5 block text-xs font-semibold text-slate-700">First name</label>
                  <input id="first-name" value={first} onChange={(e) => setFirst(e.target.value)} maxLength={100} autoComplete="given-name" className={inputCls} />
                </div>
                <div>
                  <label htmlFor="last-name" className="mb-1.5 block text-xs font-semibold text-slate-700">Last name</label>
                  <input id="last-name" value={last} onChange={(e) => setLast(e.target.value)} maxLength={100} autoComplete="family-name" className={inputCls} />
                </div>
              </div>
              <div className="flex gap-2">
                <button type="submit" disabled={!canSave || saving}
                  className="rounded-lg bg-indigo-600 px-3.5 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400">
                  {saving ? 'Saving…' : 'Save'}
                </button>
                <button type="button" onClick={() => { setEditing(false); setFirst(firstName); setLast(lastName) }}
                  className="rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">
                  Cancel
                </button>
              </div>
            </form>
          ) : (
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-lg font-bold text-slate-900">{[firstName, lastName].filter(Boolean).join(' ') || email}</p>
                <p className="mt-0.5 flex items-center gap-2 text-sm text-slate-500">
                  {orgName && <span>{orgName}</span>}
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold capitalize ${role === 'admin' ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-600'}`}>{role}</span>
                </p>
              </div>
              <button onClick={() => setEditing(true)} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50">
                Edit name
              </button>
            </div>
          )}
        </div>
      </div>
      <div className="mt-5 border-t border-slate-100 pt-4">
        <p className="text-xs font-semibold text-slate-700">Email</p>
        <p className="mt-1 flex items-center gap-1.5 text-sm text-slate-900">
          <Svg d={ICON.lock} className="h-3.5 w-3.5 text-slate-400" /> {email}
        </p>
        <p className="mt-1 text-[11px] text-slate-400">Your sign-in email can’t be changed here. Ask your administrator if it needs updating.</p>
      </div>
    </div>
  )
}

function PasswordSection({ token, onToast, onPasswordChanged }: Pick<Props, 'token' | 'onToast' | 'onPasswordChanged'>) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const rules = [
    { ok: next.length >= 8, label: 'At least 8 characters' },
    { ok: next.length > 0 && next !== current, label: 'Different from your current password' },
    { ok: confirm.length > 0 && confirm === next, label: 'Both new passwords match' },
  ]
  const valid = current.length > 0 && rules.every((r) => r.ok)
  const strength = strengthOf(next)
  const meter = [
    { label: '', bar: '' }, { label: 'Weak', bar: 'bg-red-400' }, { label: 'Fair', bar: 'bg-amber-400' },
    { label: 'Good', bar: 'bg-blue-400' }, { label: 'Strong', bar: 'bg-emerald-500' },
  ][strength]

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!valid) return
    setSaving(true); setError(null)
    try {
      const r = await fetch('/auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ current_password: current, new_password: next }),
      })
      const d = await r.json()
      if (!r.ok) { setError(d?.detail?.error ?? 'Could not change your password.'); return }
      setCurrent(''); setNext(''); setConfirm('')
      const n: number = d.other_sessions_signed_out ?? 0
      onToast(n > 0 ? `Password updated — signed out of ${n} other session${n > 1 ? 's' : ''}.` : 'Password updated.', 'success')
      onPasswordChanged(d.access_token)
    } catch {
      setError('Network error — please try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <PasswordInput id="current-password" label="Current password" value={current} onChange={setCurrent} autoComplete="current-password" />
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <PasswordInput id="new-password" label="New password" value={next} onChange={setNext} autoComplete="new-password" />
          {next && (
            <div className="mt-2 flex items-center gap-2" aria-live="polite">
              <div className="flex flex-1 gap-1">{[1, 2, 3, 4].map((l) => <span key={l} className={`h-1 flex-1 rounded-full ${l <= strength ? meter.bar : 'bg-slate-100'}`} />)}</div>
              <span className="w-12 text-right text-[11px] font-semibold text-slate-500">{meter.label}</span>
            </div>
          )}
        </div>
        <PasswordInput id="confirm-password" label="Confirm new password" value={confirm} onChange={setConfirm} autoComplete="new-password" />
      </div>
      <ul className="space-y-1" aria-label="Password requirements">
        {rules.map((r) => (
          <li key={r.label} className={`flex items-center gap-2 text-xs ${r.ok ? 'text-emerald-700' : 'text-slate-500'}`}>
            <span className={`flex h-4 w-4 items-center justify-center rounded-full ${r.ok ? 'bg-emerald-100' : 'bg-slate-100'}`}>
              <Svg d={r.ok ? ICON.check : ICON.dot} className="h-2.5 w-2.5" />
            </span>
            {r.label}
          </li>
        ))}
      </ul>
      {error && <p role="alert" className="rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs font-medium text-red-700">{error}</p>}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
        <p className="text-xs text-slate-500">For your security, this signs you out on all other devices.</p>
        <button type="submit" disabled={!valid || saving}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400 disabled:shadow-none">
          {saving ? 'Updating…' : 'Update password'}
        </button>
      </div>
    </form>
  )
}

function SessionsSection({ token, onToast }: Pick<Props, 'token' | 'onToast'>) {
  const [sessions, setSessions] = useState<ActiveSession[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [confirmAll, setConfirmAll] = useState(false)

  const load = useCallback(async () => {
    try {
      const r = await fetch('/auth/sessions', { headers: { Authorization: `Bearer ${token}` } })
      if (r.ok) setSessions((await r.json()).sessions)
    } catch { /* keep last */ }
  }, [token])
  useEffect(() => { load() }, [load])

  async function signOutOne(jti: string) {
    setBusy(jti)
    try {
      const r = await fetch(`/auth/sessions/${jti}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
      if (r.ok) { setSessions((p) => (p ?? []).filter((s) => s.jti !== jti)); onToast('Signed out of that session.', 'success') }
      else onToast('Could not sign out of that session.', 'error')
    } finally { setBusy(null) }
  }

  async function signOutOthers() {
    setBusy('all')
    try {
      const r = await fetch('/auth/sessions', { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
      if (r.ok) {
        const n = (await r.json()).signed_out as number
        onToast(`Signed out of ${n} other session${n === 1 ? '' : 's'}.`, 'success')
        await load()
      } else onToast('Could not sign out other sessions.', 'error')
    } finally { setBusy(null); setConfirmAll(false) }
  }

  const ordered = [...(sessions ?? [])].sort((a, b) => Number(b.is_current) - Number(a.is_current))
  const others = ordered.filter((s) => !s.is_current).length

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      {sessions === null ? (
        <div className="space-y-3 p-5">{[0, 1].map((i) => <div key={i} className="h-12 animate-pulse rounded-lg bg-slate-100" />)}</div>
      ) : (
        <ul className="divide-y divide-slate-100">
          {ordered.map((s) => {
            const dev = describeDevice(s.user_agent)
            return (
              <li key={s.jti} className="flex items-center gap-3.5 px-5 py-3.5">
                <span className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl ${s.is_current ? 'bg-indigo-50 text-indigo-600' : 'bg-slate-100 text-slate-500'}`}>
                  <Svg d={dev.mobile ? ICON.phone : ICON.desktop} className="h-5 w-5" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-slate-900">
                    {dev.label}
                    {s.is_current && <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700">This device</span>}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-500">
                    Signed in {ago(s.created_at)} · expires in {inFuture(s.expires_at)}{s.ip_address && <> · {s.ip_address}</>}
                  </p>
                </div>
                {!s.is_current && (
                  <button onClick={() => signOutOne(s.jti)} disabled={busy !== null}
                    className="flex-shrink-0 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:border-red-200 hover:bg-red-50 hover:text-red-700 disabled:opacity-40">
                    {busy === s.jti ? 'Signing out…' : 'Sign out'}
                  </button>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {others > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 bg-slate-50/60 px-5 py-3">
          <p className="text-xs text-slate-500">Don’t recognise a session? Sign it out, then change your password.</p>
          {confirmAll ? (
            <span className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-700">Sign out {others} other session{others > 1 ? 's' : ''}?</span>
              <button onClick={signOutOthers} disabled={busy !== null} className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700 disabled:opacity-50">
                {busy === 'all' ? 'Signing out…' : 'Yes, sign out'}
              </button>
              <button onClick={() => setConfirmAll(false)} className="rounded-lg px-2 py-1.5 text-xs font-semibold text-slate-500 hover:text-slate-700">Cancel</button>
            </span>
          ) : (
            <button onClick={() => setConfirmAll(true)} className="rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50">
              Sign out all other sessions
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function AccountSettings(props: Props) {
  return (
    <div className="fade-in">
      <div className="mb-8">
        <h2 className="text-2xl font-extrabold tracking-tight text-slate-900">Account settings</h2>
        <p className="mt-1 text-sm text-slate-500">Manage your profile, password and where you’re signed in.</p>
      </div>

      <Section title="Profile" description="How you appear to your organisation’s support team.">
        <ProfileSection {...props} />
      </Section>

      <Section title="Password" description="Use a strong password you don’t use anywhere else.">
        <PasswordSection token={props.token} onToast={props.onToast} onPasswordChanged={props.onPasswordChanged} />
      </Section>

      <Section title="Where you’re signed in" description="Devices and browsers currently signed in to your account.">
        <SessionsSection token={props.token} onToast={props.onToast} />
      </Section>

      <Section title="Sign out" description="End your session on this device.">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
          <p className="text-sm text-slate-600">You’ll need to sign in again to use NeuraDesk on this device.</p>
          <button onClick={props.onLogout} className="rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50">
            Sign out
          </button>
        </div>
      </Section>
    </div>
  )
}
