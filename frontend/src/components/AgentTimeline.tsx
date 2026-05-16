import { useEffect, useRef, useState } from 'react'

interface Props {
  ticketId: string
  text: string
  userId: string
  imageB64: string | null
  onReset: () => void
}

interface Step {
  node: string
  label: string
  isDone: boolean
}

interface FinalResult {
  resolution?: string
  status?: string
  escalation_reason?: string
  assignee_group?: string
  trace_url?: string
}

type WsMessage = {
  node: string
  status: string
  output?: Record<string, string>
  error?: string
}

const NODE_LABELS: Record<string, string> = {
  intake_node: 'Triaging ticket',
  knowledge_node: 'Searching knowledge base',
  action_node: 'Executing action',
  escalation_node: 'Escalating to human queue',
}

const BASE_STEPS: { node: string; label: string }[] = [
  { node: 'intake_node', label: NODE_LABELS.intake_node },
  { node: 'knowledge_node', label: NODE_LABELS.knowledge_node },
  { node: 'action_node', label: NODE_LABELS.action_node },
]

function CheckIcon() {
  return (
    <svg className="w-5 h-5 text-green-500 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 00-1.414 0L8 12.586 4.707 9.293a1 1 0 00-1.414 1.414l4 4a1 1 0 001.414 0l8-8a1 1 0 000-1.414z" clipRule="evenodd" />
    </svg>
  )
}

function Spinner() {
  return (
    <svg className="w-5 h-5 text-indigo-500 animate-spin flex-shrink-0" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

export default function AgentTimeline({ ticketId, text, userId, imageB64, onReset }: Props) {
  const [steps, setSteps] = useState<Step[]>(
    BASE_STEPS.map((s) => ({ ...s, isDone: false }))
  )
  const [escalationStep, setEscalationStep] = useState<Step | null>(null)
  const [isComplete, setIsComplete] = useState(false)
  const [wsError, setWsError] = useState<string | null>(null)
  // Accumulate final result fields across multiple node events
  const finalRef = useRef<FinalResult>({})
  // Force a re-render when finalRef updates on completion
  const [finalSnapshot, setFinalSnapshot] = useState<FinalResult>({})

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/${ticketId}`)

    ws.onopen = () => {
      ws.send(JSON.stringify({ text, user_id: userId, image_b64: imageB64 }))
    }

    ws.onmessage = (ev: MessageEvent<string>) => {
      const msg = JSON.parse(ev.data) as WsMessage

      if (msg.status === 'error') {
        setWsError(msg.error ?? 'Agent error — check backend logs')
        setIsComplete(true)
        return
      }

      if (msg.node === 'graph' && msg.status === 'complete') {
        setFinalSnapshot({ ...finalRef.current })
        setIsComplete(true)
        return
      }

      const out = msg.output ?? {}

      // Accumulate fields that build the final result card
      if (out.resolution) finalRef.current.resolution = out.resolution
      if (out.status) finalRef.current.status = out.status
      if (out.escalation_reason) finalRef.current.escalation_reason = out.escalation_reason
      if (out.assignee_group) finalRef.current.assignee_group = out.assignee_group
      if (out.trace_url) finalRef.current.trace_url = out.trace_url

      if (msg.node === 'escalation_node') {
        setEscalationStep({ node: 'escalation_node', label: NODE_LABELS.escalation_node, isDone: true })
      } else {
        setSteps((prev) =>
          prev.map((s) => (s.node === msg.node ? { ...s, isDone: true } : s))
        )
      }
    }

    ws.onerror = () => setWsError('WebSocket connection failed — is the backend running?')

    return () => { ws.close() }
  }, [ticketId, text, userId, imageB64])

  const allSteps = [...steps, ...(escalationStep ? [escalationStep] : [])]
  const doneCount = allSteps.filter((s) => s.isDone).length
  // Index of the step currently in progress (spinner shown); -1 when complete
  const inProgressIdx = isComplete ? -1 : doneCount
  const isEscalated =
    finalSnapshot.status === 'escalated' || Boolean(finalSnapshot.escalation_reason)

  return (
    <div className="space-y-4">
      {/* Agent steps card */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-1">Processing Ticket</h2>
        <p className="text-sm text-gray-500 mb-5 line-clamp-2">{text}</p>

        <ol className="space-y-3" aria-label="Agent processing steps">
          {allSteps.map((step, i) => (
            <li key={step.node} className="flex items-center gap-3">
              {step.isDone ? (
                <CheckIcon />
              ) : i === inProgressIdx && !wsError ? (
                <Spinner />
              ) : (
                <span className="w-5 h-5 flex items-center justify-center flex-shrink-0" aria-hidden="true">
                  <span className="w-2 h-2 rounded-full bg-gray-300" />
                </span>
              )}
              <span
                className={`text-sm ${
                  step.isDone
                    ? 'text-gray-900 font-medium'
                    : i === inProgressIdx
                    ? 'text-indigo-700 font-medium'
                    : 'text-gray-400'
                }`}
              >
                {step.label}
                {i === inProgressIdx && !step.isDone && '…'}
              </span>
            </li>
          ))}

          {/* Escalation step shown as "optional" hint until it fires */}
          {!escalationStep && !isComplete && (
            <li className="flex items-center gap-3 text-gray-300" aria-hidden="true">
              <span className="w-5 h-5 flex items-center justify-center flex-shrink-0">
                <span className="w-2 h-2 rounded-full bg-gray-200" />
              </span>
              <span className="text-sm">Escalating to human queue (if needed)</span>
            </li>
          )}
        </ol>
      </div>

      {/* Final result card — shown only after graph completes */}
      {isComplete && !wsError && (
        <div
          className={`bg-white rounded-lg shadow-sm border p-6 ${
            isEscalated ? 'border-amber-200' : 'border-green-200'
          }`}
          role="status"
          aria-live="polite"
        >
          {isEscalated ? (
            <>
              <div className="flex items-center gap-2 mb-3">
                <span className="text-amber-500 text-lg" aria-hidden="true">⚠</span>
                <h3 className="font-semibold text-gray-900">Escalated to Human Queue</h3>
              </div>
              {finalSnapshot.escalation_reason && (
                <p className="text-sm text-gray-700 mb-2">{finalSnapshot.escalation_reason}</p>
              )}
              {finalSnapshot.assignee_group && (
                <p className="text-sm text-gray-500">
                  Assigned to:{' '}
                  <span className="font-medium text-gray-700">{finalSnapshot.assignee_group}</span>
                </p>
              )}
            </>
          ) : (
            <>
              <div className="flex items-center gap-2 mb-3">
                <span className="text-green-500 text-lg" aria-hidden="true">✓</span>
                <h3 className="font-semibold text-gray-900">Resolved</h3>
              </div>
              {finalSnapshot.resolution ? (
                <p className="text-sm text-gray-700">{finalSnapshot.resolution}</p>
              ) : (
                <p className="text-sm text-gray-500">Ticket processed successfully.</p>
              )}
            </>
          )}

          {finalSnapshot.trace_url && (
            <a
              href={finalSnapshot.trace_url}
              target="_blank"
              rel="noreferrer"
              className="inline-block mt-4 text-xs text-indigo-600 hover:underline"
            >
              View LangSmith trace →
            </a>
          )}
        </div>
      )}

      {/* Error card */}
      {wsError && (
        <div
          className="bg-white rounded-lg shadow-sm border border-red-200 p-6"
          role="alert"
        >
          <p className="text-sm text-red-600 font-medium mb-1">Error</p>
          <p className="text-sm text-red-500">{wsError}</p>
        </div>
      )}

      {/* Reset button — only after completion */}
      {isComplete && (
        <button
          onClick={onReset}
          className="w-full border border-gray-300 rounded-md py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
        >
          Submit another ticket
        </button>
      )}
    </div>
  )
}
