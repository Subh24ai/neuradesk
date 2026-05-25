import { useEffect, useRef, useState } from 'react'

interface Props {
  onLogin: (token: string) => void
}

type Tab = 'login' | 'register'
type Step = 'credentials' | 'otp' | 'forgot' | 'reset-otp'
type OrgMode = 'create' | 'join'

const FEATURES = [
  {
    icon: (
      <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
      </svg>
    ),
    text: 'Auto-resolves IT & HR tickets instantly',
  },
  {
    icon: (
      <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path fillRule="evenodd" d="M10 1a4.5 4.5 0 00-4.5 4.5V9H5a2 2 0 00-2 2v6a2 2 0 002 2h10a2 2 0 002-2v-6a2 2 0 00-2-2h-.5V5.5A4.5 4.5 0 0010 1zm3 8V5.5a3 3 0 10-6 0V9h6z" clipRule="evenodd" />
      </svg>
    ),
    text: 'Full audit trail on every AI decision',
  },
  {
    icon: (
      <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path d="M11 17a1 1 0 001.447.894l4-2A1 1 0 0017 15V9.236a1 1 0 00-1.447-.894l-4 2a1 1 0 00-.553.894V17zM15.211 6.276a1 1 0 000-1.788l-4.764-2.382a1 1 0 00-.894 0L4.789 4.488a1 1 0 000 1.788l4.764 2.382a1 1 0 00.894 0l4.764-2.382zM4.447 8.342A1 1 0 003 9.236V15a1 1 0 00.553.894l4 2A1 1 0 009 17v-5.764a1 1 0 00-.553-.894l-4-2z" />
      </svg>
    ),
    text: 'Multi-tenant with role-based access',
  },
]

function Spinner() {
  return (
    <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

function InputField({
  id, label, type, value, onChange, placeholder, autoComplete, required, minLength, autoFocus, children,
}: {
  id: string; label: string; type: string; value: string; onChange: (v: string) => void;
  placeholder?: string; autoComplete?: string; required?: boolean; minLength?: number; autoFocus?: boolean;
  children?: React.ReactNode
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-semibold text-slate-500 uppercase tracking-widest mb-1.5">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type={type}
          required={required}
          autoComplete={autoComplete}
          minLength={minLength}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          // eslint-disable-next-line jsx-a11y/no-autofocus
          autoFocus={autoFocus}
          className="w-full border border-slate-200 rounded-xl px-3.5 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-shadow hover:border-slate-300 bg-slate-50/50 focus:bg-white"
        />
        {children}
      </div>
    </div>
  )
}

function BrandPanel() {
  return (
    <div className="relative bg-gradient-to-br from-indigo-700 via-indigo-600 to-violet-700 px-8 pt-10 pb-8 lg:h-full lg:flex lg:flex-col overflow-hidden">
      {/* Decorative circles */}
      <div aria-hidden="true" className="absolute pointer-events-none inset-0 overflow-hidden">
        <div className="absolute -top-20 -right-20 w-72 h-72 rounded-full bg-white/5" />
        <div className="absolute top-1/3 -right-12 w-40 h-40 rounded-full bg-violet-500/20" />
        <div className="absolute -bottom-20 -left-12 w-64 h-64 rounded-full bg-indigo-900/30" />
      </div>

      {/* Logo + wordmark */}
      <div className="relative z-10 flex items-center gap-3 mb-10">
        <div className="w-11 h-11 bg-white/15 backdrop-blur-sm rounded-2xl flex items-center justify-center shadow-inner flex-shrink-0">
          <svg viewBox="0 0 24 24" className="w-6 h-6" fill="none" aria-hidden="true">
            <line x1="12" y1="4.5" x2="12" y2="12.5" stroke="white" strokeWidth="1.8" strokeLinecap="round" opacity="0.75"/>
            <line x1="5.5" y1="19.5" x2="12" y2="12.5" stroke="white" strokeWidth="1.8" strokeLinecap="round" opacity="0.75"/>
            <line x1="18.5" y1="19.5" x2="12" y2="12.5" stroke="white" strokeWidth="1.8" strokeLinecap="round" opacity="0.75"/>
            <circle cx="12" cy="4.5" r="2.25" fill="white"/>
            <circle cx="5.5" cy="19.5" r="2.25" fill="white" opacity="0.85"/>
            <circle cx="18.5" cy="19.5" r="2.25" fill="white" opacity="0.85"/>
            <circle cx="12" cy="12.5" r="3.25" fill="white"/>
          </svg>
        </div>
        <div>
          <p className="text-xl font-bold text-white tracking-tight leading-none">NeuraDesk</p>
          <p className="text-indigo-300/80 text-[11px] font-medium tracking-widest uppercase mt-1">AI Service Desk</p>
        </div>
      </div>

      {/* Headline + description */}
      <div className="relative z-10 flex-1">
        <h2 className="text-3xl font-bold text-white leading-snug mb-3">
          IT &amp; HR tickets,<br/><span className="text-indigo-200">resolved in seconds.</span>
        </h2>
        <p className="text-indigo-200/80 text-sm leading-relaxed mb-8 max-w-[260px]">
          Four specialized AI agents work in concert to triage, retrieve, execute, and escalate — automatically.
        </p>
        <div className="space-y-3">
          {FEATURES.map(({ icon, text }) => (
            <div key={text} className="flex items-center gap-3">
              <div className="w-7 h-7 rounded-lg bg-white/10 flex items-center justify-center text-white flex-shrink-0">
                {icon}
              </div>
              <span className="text-indigo-100 text-sm">{text}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Stats row */}
      <div className="relative z-10 mt-auto pt-7 border-t border-white/10 grid grid-cols-3 gap-4">
        {[
          { val: '4', label: 'AI Agents' },
          { val: '<2s', label: 'Avg resolve' },
          { val: 'SOC2', label: 'Ready' },
        ].map(({ val, label }) => (
          <div key={label} className="text-center">
            <p className="text-white font-bold text-lg leading-none">{val}</p>
            <p className="text-indigo-300/70 text-[11px] mt-1 font-medium">{label}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function LoginForm({ onLogin }: Props) {
  const [tab, setTab] = useState<Tab>('login')
  const [step, setStep] = useState<Step>('credentials')
  const [email, setEmail] = useState('')
  const [emailError, setEmailError] = useState<string | null>(null)
  const [password, setPassword] = useState('')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [orgMode, setOrgMode] = useState<OrgMode>('create')
  const [orgName, setOrgName] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [orgCreationToken, setOrgCreationToken] = useState('')
  const [orgCreationRestricted, setOrgCreationRestricted] = useState(false)
  const [workEmailRequired, setWorkEmailRequired] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const [pendingEmail, setPendingEmail] = useState('')
  const [otpDigits, setOtpDigits] = useState<string[]>(Array(6).fill(''))
  const [resendCooldown, setResendCooldown] = useState(0)
  const [devOtp, setDevOtp] = useState<string | null>(null)
  const otpRefs = useRef<(HTMLInputElement | null)[]>([])

  const [newPassword, setNewPassword] = useState('')
  const [forgotEmail, setForgotEmail] = useState('')

  useEffect(() => {
    if (resendCooldown <= 0) return
    const id = setTimeout(() => setResendCooldown((c) => c - 1), 1000)
    return () => clearTimeout(id)
  }, [resendCooldown])

  useEffect(() => {
    if (step === 'otp' && otpDigits.every((d) => d) && !loading) {
      handleOtpSubmit(otpDigits.join(''))
    }
  }, [otpDigits, step])

  useEffect(() => {
    fetch('/auth/config')
      .then((r) => r.json())
      .then((d) => {
        if (d.org_creation_restricted) setOrgCreationRestricted(true)
        if (d.work_email_required) setWorkEmailRequired(true)
      })
      .catch(() => {})
  }, [])

  async function handleOtpSubmit(otp: string) {
    if (loading) return
    setError(null)
    setLoading(true)
    try {
      const res = await fetch('/auth/verify-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: pendingEmail, otp }),
      })
      const data = await res.json() as { access_token?: string; detail?: { error?: string } | string }
      if (!res.ok) {
        const detail = data.detail
        setError(typeof detail === 'string' ? detail : (detail?.error ?? 'Invalid code'))
        setOtpDigits(Array(6).fill(''))
        setTimeout(() => otpRefs.current[0]?.focus(), 50)
        return
      }
      if (tab === 'register') {
        switchTab('login')
        setSuccess('Account verified! Please sign in.')
        return
      }
      onLogin(data.access_token!)
    } catch {
      setError('Network error — is the backend running on port 8000?')
    } finally {
      setLoading(false)
    }
  }

  function handleOtpInput(index: number, value: string) {
    const digit = value.replace(/\D/g, '').slice(-1)
    const next = [...otpDigits]
    next[index] = digit
    setOtpDigits(next)
    if (digit && index < 5) otpRefs.current[index + 1]?.focus()
    if (digit && index === 5 && next.every((d) => d !== '')) handleOtpSubmit(next.join(''))
  }

  function handleOtpKeyDown(index: number, e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Backspace' && !otpDigits[index] && index > 0) otpRefs.current[index - 1]?.focus()
    if (e.key === 'ArrowLeft' && index > 0) otpRefs.current[index - 1]?.focus()
    if (e.key === 'ArrowRight' && index < 5) otpRefs.current[index + 1]?.focus()
  }

  function handleOtpPaste(e: React.ClipboardEvent) {
    e.preventDefault()
    const text = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6)
    if (!text) return
    const next = Array(6).fill('')
    for (let i = 0; i < text.length; i++) next[i] = text[i]
    setOtpDigits(next)
    otpRefs.current[Math.min(text.length, 5)]?.focus()
    if (next.every((d) => d !== '')) handleOtpSubmit(next.join(''))
  }

  async function handleResend() {
    if (resendCooldown > 0) return
    setError(null)
    try {
      const res = await fetch('/auth/resend-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: pendingEmail }),
      })
      const data = res.ok ? await res.json() as { dev_otp?: string } : {}
      const devDigits = data.dev_otp ? data.dev_otp.split('') : Array(6).fill('')
      setOtpDigits(devDigits)
      setResendCooldown(60)
      setTimeout(() => otpRefs.current[data.dev_otp ? 5 : 0]?.focus(), 50)
    } catch {
      setError('Failed to resend code')
    }
  }

  async function handleForgotSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await fetch('/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: forgotEmail }),
      })
      setPendingEmail(forgotEmail)
      setOtpDigits(Array(6).fill(''))
      setNewPassword('')
      setResendCooldown(60)
      setStep('reset-otp')
      setTimeout(() => otpRefs.current[0]?.focus(), 50)
    } catch {
      setError('Network error — is the backend running on port 8000?')
    } finally {
      setLoading(false)
    }
  }

  async function handleResetSubmit() {
    const otp = otpDigits.join('')
    if (otp.length < 6 || !newPassword) return
    setError(null)
    setLoading(true)
    try {
      const res = await fetch('/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: pendingEmail, otp, new_password: newPassword }),
      })
      const data = await res.json() as { access_token?: string; detail?: { error?: string } | string }
      if (!res.ok) {
        const detail = data.detail
        setError(typeof detail === 'string' ? detail : (detail?.error ?? 'Reset failed'))
        setOtpDigits(Array(6).fill(''))
        setTimeout(() => otpRefs.current[0]?.focus(), 50)
        return
      }
      onLogin(data.access_token!)
    } catch {
      setError('Network error — is the backend running on port 8000?')
    } finally {
      setLoading(false)
    }
  }

  const PERSONAL_DOMAINS = new Set([
    'gmail.com','yahoo.com','hotmail.com','outlook.com','live.com',
    'icloud.com','me.com','mac.com','aol.com','protonmail.com',
    'proton.me','ymail.com','msn.com','mail.com','gmx.com',
    'zoho.com','yandex.com','inbox.com','fastmail.com','hey.com',
  ])

  function handleEmailChange(value: string) {
    setEmail(value)
    if (workEmailRequired && tab === 'register' && value.includes('@')) {
      const domain = value.split('@').pop()?.toLowerCase() ?? ''
      setEmailError(PERSONAL_DOMAINS.has(domain) ? 'Please use your work email, not a personal one' : null)
    } else {
      setEmailError(null)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      if (tab === 'login') {
        const res = await fetch('/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        })
        const data = await res.json() as { access_token?: string; detail?: { error?: string; code?: string } | string }
        if (!res.ok) {
          const detail = data.detail
          const code = typeof detail === 'object' ? detail?.code : undefined
          if (code === 'EMAIL_NOT_VERIFIED') {
            setPendingEmail(email)
            setOtpDigits(Array(6).fill(''))
            setResendCooldown(0)
            setStep('otp')
            setTimeout(() => otpRefs.current[0]?.focus(), 50)
            return
          }
          setError(typeof detail === 'string' ? detail : (detail?.error ?? 'Authentication failed'))
          return
        }
        onLogin(data.access_token!)
      } else {
        const body = orgMode === 'create'
          ? { email, password, first_name: firstName, last_name: lastName, org_name: orgName, ...(orgCreationToken ? { org_creation_token: orgCreationToken } : {}) }
          : { email, password, first_name: firstName, last_name: lastName, invite_code: inviteCode }
        const res = await fetch('/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
        const data = await res.json() as { message?: string; dev_otp?: string; detail?: { error?: string } | string }
        if (!res.ok) {
          const detail = data.detail
          setError(typeof detail === 'string' ? detail : (detail?.error ?? 'Registration failed'))
          return
        }
        setPendingEmail(email)
        setOtpDigits(Array(6).fill(''))
        setDevOtp(data.dev_otp ?? null)
        setResendCooldown(60)
        setStep('otp')
        setTimeout(() => otpRefs.current[0]?.focus(), 50)
      }
    } catch {
      setError('Network error — is the backend running on port 8000?')
    } finally {
      setLoading(false)
    }
  }

  function switchTab(t: Tab) {
    setTab(t)
    setStep('credentials')
    setError(null)
    setSuccess(null)
    setEmail('')
    setEmailError(null)
    setPassword('')
    setShowPassword(false)
    setFirstName('')
    setLastName('')
  }

  // ── Shared OTP input ──────────────────────────────────────────────────────────
  function OtpInputRow() {
    return (
      <div className="flex gap-2">
        {otpDigits.map((digit, i) => (
          <input
            key={i}
            ref={(el) => { otpRefs.current[i] = el }}
            type="text"
            inputMode="numeric"
            maxLength={1}
            value={digit}
            onChange={(e) => handleOtpInput(i, e.target.value)}
            onKeyDown={(e) => handleOtpKeyDown(i, e)}
            onPaste={i === 0 ? handleOtpPaste : undefined}
            className={`flex-1 min-w-0 h-14 text-center text-2xl font-bold border-2 rounded-xl text-slate-900 focus:outline-none transition-all caret-transparent ${
              digit
                ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
                : 'border-slate-200 bg-white focus:border-indigo-400 focus:bg-indigo-50/30'
            }`}
            aria-label={`Digit ${i + 1}`}
          />
        ))}
      </div>
    )
  }

  function ErrorAlert() {
    if (!error) return null
    return (
      <div role="alert" className="flex items-start gap-2 text-sm text-red-700 bg-red-50 border border-red-100 rounded-xl px-3.5 py-2.5 scale-in">
        <svg className="w-4 h-4 mt-0.5 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
        </svg>
        {error}
      </div>
    )
  }

  function SuccessAlert() {
    if (!success) return null
    return (
      <div role="status" className="flex items-start gap-2 text-sm text-emerald-700 bg-emerald-50 border border-emerald-100 rounded-xl px-3.5 py-2.5 scale-in">
        <svg className="w-4 h-4 mt-0.5 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
        </svg>
        {success}
      </div>
    )
  }

  const shell = (formContent: React.ReactNode) => (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm sm:max-w-md md:max-w-lg lg:max-w-4xl fade-in">
        <div className="bg-white rounded-2xl shadow-2xl overflow-hidden ring-1 ring-slate-900/5 lg:flex lg:min-h-[560px]">
          {/* Left brand panel — desktop only */}
          <div className="hidden lg:flex lg:w-80 xl:w-96 shrink-0">
            <BrandPanel />
          </div>
          {/* Form column */}
          <div className="flex-1 flex flex-col">
            {/* Mobile brand panel */}
            <div className="lg:hidden">
              <BrandPanel />
            </div>
            {formContent}
          </div>
        </div>
      </div>
    </div>
  )

  // ── OTP verification ──────────────────────────────────────────────────────────
  function maskEmail(e: string) {
    const [local, domain] = e.split('@')
    if (!domain) return e
    const visible = local.length <= 3 ? local[0] : local.slice(0, 3)
    return `${visible}${'*'.repeat(Math.max(2, local.length - 3))}@${domain}`
  }

  const filledCount = otpDigits.filter(Boolean).length

  if (step === 'otp') return shell(
    <div className="px-8 py-8 flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col items-center text-center gap-3">
        <div className="w-14 h-14 rounded-2xl bg-indigo-50 flex items-center justify-center ring-1 ring-indigo-100">
          <svg className="w-7 h-7 text-indigo-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
          </svg>
        </div>
        <div>
          <h2 className="text-xl font-bold text-slate-900">Check your email</h2>
          <p className="mt-1 text-sm text-slate-500">
            We sent a 6-digit code to
          </p>
          <p className="mt-0.5 text-sm font-semibold text-slate-800">{maskEmail(pendingEmail)}</p>
        </div>
      </div>

      {/* OTP inputs */}
      <div>
        <OtpInputRow />
        {/* Progress dots */}
        <div className="flex justify-center gap-1.5 mt-3">
          {Array(6).fill(null).map((_, i) => (
            <div key={i} className={`h-1 rounded-full transition-all duration-200 ${i < filledCount ? 'w-5 bg-indigo-500' : 'w-2 bg-slate-200'}`} />
          ))}
        </div>
      </div>

      <ErrorAlert />

      {/* Verify button */}
      <button
        type="button"
        onClick={() => handleOtpSubmit(otpDigits.join(''))}
        disabled={loading || otpDigits.some((d) => !d)}
        className="w-full bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-700 hover:to-violet-700 text-white rounded-xl py-3 text-sm font-semibold disabled:opacity-40 transition-all shadow-sm hover:shadow-md"
      >
        {loading ? <span className="flex items-center justify-center gap-2"><Spinner />Verifying…</span> : 'Verify email'}
      </button>

      {/* Footer actions */}
      <div className="flex items-center justify-between text-sm">
        <button type="button" onClick={() => { setStep('credentials'); setError(null) }} className="text-slate-400 hover:text-slate-700 font-medium transition-colors">
          ← Back
        </button>
        <button
          type="button"
          onClick={handleResend}
          disabled={resendCooldown > 0}
          className="font-semibold transition-colors disabled:text-slate-300 text-indigo-600 hover:text-indigo-800"
        >
          {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : 'Resend code'}
        </button>
      </div>

      {/* Dev helper — only visible when SMTP is not configured */}
      {devOtp && (
        <details className="rounded-xl border border-dashed border-amber-300 bg-amber-50 text-xs text-amber-800">
          <summary className="cursor-pointer px-3.5 py-2.5 font-semibold select-none list-none flex items-center gap-2">
            <svg className="w-3.5 h-3.5 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
            </svg>
            Dev mode — click to reveal OTP
          </summary>
          <div className="px-3.5 pb-3 pt-1 flex items-center justify-between gap-3">
            <span className="text-slate-500">SMTP not configured — real emails are not sent in dev.</span>
            <span className="font-mono font-bold text-base tracking-widest text-amber-900 whitespace-nowrap">{devOtp}</span>
          </div>
        </details>
      )}
    </div>
  )

  // ── Forgot password ───────────────────────────────────────────────────────────
  if (step === 'forgot') return shell(
    <form onSubmit={handleForgotSubmit} className="px-8 py-7 space-y-5">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Reset password</h2>
          <p className="mt-1 text-sm text-slate-500">We'll send a 6-digit code to your email.</p>
        </div>
        <InputField id="forgot-email" label="Work email" type="email" required autoFocus
          value={forgotEmail} onChange={setForgotEmail} placeholder="you@company.com" />
        <ErrorAlert />
        <button type="submit" disabled={loading}
          className="w-full bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-700 hover:to-violet-700 text-white rounded-xl py-3 text-sm font-semibold disabled:opacity-40 transition-all shadow-sm hover:shadow-md">
          {loading ? <span className="flex items-center justify-center gap-2"><Spinner />Sending…</span> : 'Send reset code'}
        </button>
        <button type="button" onClick={() => { setStep('credentials'); setError(null) }}
          className="w-full text-sm text-slate-400 hover:text-slate-700 text-center transition-colors font-medium">
          ← Back to sign in
        </button>
      </form>
  )

  // ── Reset password OTP ────────────────────────────────────────────────────────
  if (step === 'reset-otp') return shell(
    <div className="px-8 py-7 space-y-5">
        <div>
          <h2 className="text-lg font-bold text-slate-900">New password</h2>
          <p className="mt-1 text-sm text-slate-500">
            Code sent to <span className="font-semibold text-slate-800">{pendingEmail}</span>
          </p>
        </div>
        <div>
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest mb-3">Reset code</p>
          <OtpInputRow />
        </div>
        <InputField id="new-pw" label="New password" type="password" required
          value={newPassword} onChange={setNewPassword} placeholder="Min 8 characters" minLength={8} />
        <ErrorAlert />
        <button
          type="button"
          onClick={handleResetSubmit}
          disabled={loading || otpDigits.some((d) => !d) || newPassword.length < 8}
          className="w-full bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-700 hover:to-violet-700 text-white rounded-xl py-3 text-sm font-semibold disabled:opacity-40 transition-all shadow-sm hover:shadow-md"
        >
          {loading ? <span className="flex items-center justify-center gap-2"><Spinner />Resetting…</span> : 'Reset & sign in'}
        </button>
        <div className="flex items-center justify-between text-sm">
          <button type="button" onClick={() => { setStep('forgot'); setError(null) }} className="text-slate-400 hover:text-slate-700 font-medium transition-colors">
            ← Back
          </button>
          <button type="button" onClick={handleResend} disabled={resendCooldown > 0}
            className="font-semibold transition-colors disabled:text-slate-300 text-indigo-600 hover:text-indigo-800">
            {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : 'Resend code'}
          </button>
        </div>
      </div>
  )

  // ── Credentials ───────────────────────────────────────────────────────────────
  return shell(
    <>
      {/* Tab switcher */}
      <div className="flex bg-slate-50 border-b border-slate-200">
        {(['login', 'register'] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => switchTab(t)}
            className={`flex-1 py-3.5 text-sm font-semibold transition-all ${
              tab === t
                ? 'text-indigo-600 border-b-2 border-indigo-600 bg-white'
                : 'text-slate-500 hover:text-slate-800 hover:bg-white/50'
            }`}
          >
            {t === 'login' ? 'Sign in' : 'Create account'}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="px-8 py-7 space-y-4">
        {tab === 'register' && (
          <div className="grid grid-cols-2 gap-3">
            <InputField id="first-name" label="First name" type="text" required autoComplete="given-name"
              value={firstName} onChange={setFirstName} placeholder="Jane" />
            <InputField id="last-name" label="Last name" type="text" required autoComplete="family-name"
              value={lastName} onChange={setLastName} placeholder="Smith" />
          </div>
        )}
        <div>
          <InputField id="email" label="Work email" type="email" required autoComplete="email"
            value={email} onChange={handleEmailChange} placeholder="you@company.com" />
          {emailError && (
            <p className="mt-1.5 text-xs text-red-500">{emailError}</p>
          )}
        </div>

        <div>
          <label htmlFor="password" className="block text-xs font-semibold text-slate-500 uppercase tracking-widest mb-1.5">
            Password
          </label>
          <div className="relative">
            <input
              id="password"
              type={showPassword ? 'text' : 'password'}
              required
              autoComplete={tab === 'login' ? 'current-password' : 'new-password'}
              minLength={tab === 'register' ? 8 : 1}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={tab === 'register' ? 'Min 8 characters' : '••••••••'}
              className="w-full border border-slate-200 rounded-xl px-3.5 py-2.5 pr-10 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-shadow hover:border-slate-300 bg-slate-50/50 focus:bg-white"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-400 hover:text-slate-600 transition-colors"
            >
              {showPassword ? (
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

        {/* Forgot password */}
        {tab === 'login' && (
          <div className="flex justify-end -mt-1">
            <button
              type="button"
              onClick={() => { setForgotEmail(email); setStep('forgot'); setError(null) }}
              className="text-xs text-indigo-600 hover:text-indigo-800 font-semibold transition-colors"
            >
              Forgot password?
            </button>
          </div>
        )}

        {/* Organisation section */}
        {tab === 'register' && (
          <div>
            <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-widest mb-2">Organisation</p>
            <div className="flex rounded-xl border border-slate-200 overflow-hidden mb-3">
              {(['create', 'join'] as OrgMode[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => { setOrgMode(m); setError(null) }}
                  className={`flex-1 py-2.5 text-xs font-semibold transition-all ${
                    orgMode === m ? 'bg-indigo-600 text-white' : 'text-slate-500 hover:text-slate-800 hover:bg-slate-50'
                  }`}
                >
                  {m === 'create' ? 'Create new' : 'Join with code'}
                </button>
              ))}
            </div>
            {orgMode === 'create' ? (
              <>
                <input
                  type="text"
                  required={tab === 'register' && orgMode === 'create'}
                  minLength={2}
                  maxLength={100}
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                  placeholder="Acme Corp, DevOps Team…"
                  className="w-full border border-slate-200 rounded-xl px-3.5 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-shadow hover:border-slate-300 bg-slate-50/50 focus:bg-white"
                />
                {orgCreationRestricted && (
                  <div className="mt-3">
                    <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-widest mb-1.5">Admin token</p>
                    <input
                      type="password"
                      required
                      value={orgCreationToken}
                      onChange={(e) => setOrgCreationToken(e.target.value)}
                      placeholder="Provided by your platform admin"
                      className="w-full border border-slate-200 rounded-xl px-3.5 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-shadow font-mono bg-slate-50/50 focus:bg-white"
                    />
                  </div>
                )}
                <p className="text-xs text-slate-400 mt-2">
                  {orgCreationRestricted ? 'Organisation creation is restricted — provide your admin token.' : 'You become the admin. Share the invite code with your team.'}
                </p>
              </>
            ) : (
              <>
                <input
                  type="text"
                  required={tab === 'register' && orgMode === 'join'}
                  value={inviteCode}
                  onChange={(e) => setInviteCode(e.target.value)}
                  placeholder="Paste your invite code"
                  className="w-full border border-slate-200 rounded-xl px-3.5 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-shadow font-mono bg-slate-50/50 focus:bg-white"
                />
                <p className="text-xs text-slate-400 mt-2">Ask your admin for the invite code from Settings → Organisation.</p>
              </>
            )}
          </div>
        )}

        <SuccessAlert />
        <ErrorAlert />

        <button
          type="submit"
          disabled={loading || !!emailError}
          className="w-full bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-700 hover:to-violet-700 text-white rounded-xl py-3 text-sm font-semibold disabled:opacity-50 transition-all shadow-sm hover:shadow-md"
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2"><Spinner />Please wait…</span>
          ) : tab === 'login' ? 'Sign in' : 'Continue'}
        </button>
      </form>
    </>
  )
}
