// Global session guard: if any authenticated API call comes back 401 (expired
// or revoked token) or 403 ACCOUNT_DEACTIVATED, the app signs the user out and
// tells them why — instead of every page silently showing "couldn't load".

export type SessionEndReason = 'expired' | 'deactivated'
export const SESSION_ENDED_EVENT = 'nd:session-ended'

let installed = false

export function installSessionGuard(): void {
  if (installed) return
  installed = true
  const original = window.fetch.bind(window)
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const res = await original(input, init)
    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined))
    const authed = headers.get('Authorization')?.startsWith('Bearer ')
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    // Logout itself legitimately returns 401 for an already-dead token.
    if (authed && !url.includes('/auth/logout') && (res.status === 401 || res.status === 403)) {
      let reason: SessionEndReason | null = res.status === 401 ? 'expired' : null
      if (res.status === 403) {
        const body = await res.clone().json().catch(() => null)
        if (body?.detail?.code === 'ACCOUNT_DEACTIVATED') reason = 'deactivated'
      }
      if (reason) window.dispatchEvent(new CustomEvent<SessionEndReason>(SESSION_ENDED_EVENT, { detail: reason }))
    }
    return res
  }
}
