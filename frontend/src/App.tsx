import { useState } from 'react'
import LoginForm from './components/LoginForm'
import TicketForm from './components/TicketForm'
import AgentTimeline from './components/AgentTimeline'

interface Auth {
  token: string
  userId: string
  email: string
}

interface Submission {
  ticketId: string
  text: string
  imageB64: string | null
}

function decodeJwtPayload(token: string): { sub: string; email: string } {
  const payload = JSON.parse(atob(token.split('.')[1]))
  return { sub: payload.sub as string, email: payload.email as string }
}

export default function App() {
  const [auth, setAuth] = useState<Auth | null>(() => {
    const stored = sessionStorage.getItem('nd_auth')
    return stored ? (JSON.parse(stored) as Auth) : null
  })
  const [submission, setSubmission] = useState<Submission | null>(null)

  function handleLogin(token: string) {
    const { sub: userId, email } = decodeJwtPayload(token)
    const state: Auth = { token, userId, email }
    // sessionStorage preferred over localStorage — token cleared on tab close
    sessionStorage.setItem('nd_auth', JSON.stringify(state))
    setAuth(state)
  }

  function handleLogout() {
    sessionStorage.removeItem('nd_auth')
    setAuth(null)
    setSubmission(null)
  }

  function handleSubmit(text: string, imageB64: string | null) {
    setSubmission({ ticketId: crypto.randomUUID(), text, imageB64 })
  }

  if (!auth) {
    return <LoginForm onLogin={handleLogin} />
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-2xl mx-auto px-4 py-4 flex items-center justify-between">
          <span className="font-semibold text-gray-900 tracking-tight">NeuraDesk</span>
          <div className="flex items-center gap-4">
            <span className="text-sm text-gray-500 hidden sm:block">{auth.email}</span>
            <button
              onClick={handleLogout}
              className="text-sm text-gray-500 hover:text-gray-900 transition-colors"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-8">
        {submission ? (
          <AgentTimeline
            ticketId={submission.ticketId}
            text={submission.text}
            imageB64={submission.imageB64}
            userId={auth.userId}
            onReset={() => setSubmission(null)}
          />
        ) : (
          <TicketForm onSubmit={handleSubmit} />
        )}
      </main>
    </div>
  )
}
