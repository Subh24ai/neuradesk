import { useCallback, useEffect, useRef, useState } from 'react'

interface Props {
  ticketId: string
  text: string
  token: string
  imageB64: string | null
  onReset: () => void
}

interface Step {
  node: string
  label: string
  sublabel: string
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
  resolution?: string
  trace_url?: string
}

const NODE_META: Record<string, { label: string; sublabel: string; iconPath: string }> = {
  intake_node: {
    label: 'Triaging ticket',
    sublabel: 'Classifying intent and priority',
    iconPath: 'M12 3c2.755 0 5.455.232 8.083.678.533.09.917.556.917 1.096v1.044a2.25 2.25 0 01-.659 1.591l-5.432 5.432a2.25 2.25 0 00-.659 1.591v2.927a2.25 2.25 0 01-1.244 2.013L9.75 21v-6.568a2.25 2.25 0 00-.659-1.591L3.659 7.409A2.25 2.25 0 013 5.818V4.774c0-.54.384-1.006.917-1.096A48.32 48.32 0 0112 3z',
  },
  knowledge_node: {
    label: 'Searching knowledge base',
    sublabel: 'FAISS + BM25 hybrid retrieval',
    iconPath: 'M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z',
  },
  action_node: {
    label: 'Executing action',
    sublabel: 'Calling enterprise APIs',
    iconPath: 'M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z',
  },
  escalation_node: {
    label: 'Escalating to human queue',
    sublabel: 'Routing to support team',
    iconPath: 'M4.5 19.5l15-15m0 0H8.25m11.25 0v11.25',
  },
}

const BASE_STEPS: { node: string }[] = [
  { node: 'intake_node' },
  { node: 'knowledge_node' },
  { node: 'action_node' },
]

const MAX_RETRIES = 3
const RETRY_DELAY_MS = 2000

function CheckIcon() {
  return (
    <svg className="w-4 h-4 text-white" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 00-1.414 0L8 12.586 4.707 9.293a1 1 0 00-1.414 1.414l4 4a1 1 0 001.414 0l8-8a1 1 0 000-1.414z" clipRule="evenodd" />
    </svg>
  )
}

function StepIcon({ isDone, isActive, nodeKey }: { isDone: boolean; isActive: boolean; nodeKey: string }) {
  const meta = NODE_META[nodeKey]
  if (isDone) {
    return (
      <div className="w-9 h-9 rounded-full bg-emerald-500 flex items-center justify-center shadow-sm ring-4 ring-white flex-shrink-0">
        <CheckIcon />
      </div>
    )
  }
  if (isActive) {
    return (
      <div className="w-9 h-9 rounded-full bg-indigo-600 flex items-center justify-center shadow-sm ring-4 ring-indigo-100 flex-shrink-0">
        <svg className="w-4 h-4 text-white animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>
    )
  }
  return (
    <div className="w-9 h-9 rounded-full bg-slate-100 border-2 border-slate-200 flex items-center justify-center flex-shrink-0">
      {meta && (
        <svg className="w-3.5 h-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" d={meta.iconPath} />
        </svg>
      )}
    </div>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) })}
      className={`inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border transition-all ${
        copied ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-white border-slate-200 text-slate-500 hover:text-slate-700 hover:border-slate-300 hover:shadow-sm'
      }`}
      aria-label="Copy resolution text"
    >
      {copied ? (
        <><svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 00-1.414 0L8 12.586 4.707 9.293a1 1 0 00-1.414 1.414l4 4a1 1 0 001.414 0l8-8a1 1 0 000-1.414z" clipRule="evenodd" /></svg>Copied!</>
      ) : (
        <><svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path d="M7 3.5A1.5 1.5 0 018.5 2h3.879a1.5 1.5 0 011.06.44l3.122 3.12A1.5 1.5 0 0117 6.622V12.5a1.5 1.5 0 01-1.5 1.5h-1v-3.379a3 3 0 00-.879-2.121L10.5 5.379A3 3 0 008.379 4.5H7v-1z" /><path d="M4.5 6A1.5 1.5 0 003 7.5v9A1.5 1.5 0 004.5 18h7a1.5 1.5 0 001.5-1.5v-5.879a1.5 1.5 0 00-.44-1.06L9.44 6.439A1.5 1.5 0 008.378 6H4.5z" /></svg>Copy</>
      )}
    </button>
  )
}

export default function AgentTimeline({ ticketId, text, token, imageB64, onReset }: Props) {
  const [steps, setSteps] = useState<Step[]>(
    BASE_STEPS.map((s) => ({ ...s, ...NODE_META[s.node], isDone: false }))
  )
  const [escalationStep, setEscalationStep] = useState<Step | null>(null)
  const [isComplete, setIsComplete] = useState(false)
  const [wsError, setWsError] = useState<string | null>(null)
  const [retryCount, setRetryCount] = useState(0)
  const finalRef = useRef<FinalResult>({})
  const [finalSnapshot, setFinalSnapshot] = useState<FinalResult>({})
  const resolvedRef = useRef(false)
  const startTimeRef = useRef(Date.now())
  const [elapsedSec, setElapsedSec] = useState<number | null>(null)
  const [liveElapsed, setLiveElapsed] = useState(0)
  const wsRef = useRef<WebSocket | null>(null)

  const connect = useCallback(() => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/${ticketId}`)
    wsRef.current = ws

    ws.onopen = () => ws.send(JSON.stringify({ token, text, image_b64: imageB64 }))

    ws.onmessage = (ev: MessageEvent<string>) => {
      const msg = JSON.parse(ev.data) as WsMessage
      if (msg.status === 'error') {
        setWsError(msg.error ?? 'Agent error — check backend logs')
        setIsComplete(true)
        return
      }
      if (msg.node === 'graph' && msg.status === 'complete') {
        resolvedRef.current = true
        setElapsedSec(Math.round((Date.now() - startTimeRef.current) / 100) / 10)
        setFinalSnapshot({
          ...finalRef.current,
          ...(msg.resolution ? { resolution: msg.resolution } : {}),
          ...(msg.trace_url ? { trace_url: msg.trace_url } : {}),
        })
        setIsComplete(true)
        ws.close(1000, 'complete')
        return
      }
      const out = msg.output ?? {}
      if (out.resolution) finalRef.current.resolution = out.resolution
      if (out.status) finalRef.current.status = out.status
      if (out.escalation_reason) finalRef.current.escalation_reason = out.escalation_reason
      if (out.assignee_group) finalRef.current.assignee_group = out.assignee_group
      if (out.trace_url) finalRef.current.trace_url = out.trace_url
      if (msg.node === 'escalation_node') {
        setEscalationStep({ node: 'escalation_node', ...NODE_META.escalation_node, isDone: true })
      } else {
        setSteps((prev) => prev.map((s) => s.node === msg.node ? { ...s, isDone: true } : s))
      }
    }

    ws.onerror = () => { if (resolvedRef.current) return }

    ws.onclose = (ev) => {
      if (resolvedRef.current) return
      if (ev.code === 1000 || ev.code === 1008) { setWsError('Connection closed unexpectedly.'); return }
      setRetryCount((prev) => {
        if (prev >= MAX_RETRIES) { setWsError('Connection lost after multiple retries. Please try again.'); return prev }
        setTimeout(connect, RETRY_DELAY_MS * (prev + 1))
        return prev + 1
      })
    }
  }, [ticketId, text, token, imageB64])

  useEffect(() => { connect(); return () => { wsRef.current?.close() } }, [connect])

  useEffect(() => {
    if (isComplete) return
    const timer = setInterval(() => {
      setLiveElapsed(+(((Date.now() - startTimeRef.current) / 1000).toFixed(1)))
    }, 100)
    return () => clearInterval(timer)
  }, [isComplete])

  const allSteps = [...steps, ...(escalationStep ? [escalationStep] : [])]
  const doneCount = allSteps.filter((s) => s.isDone).length
  const inProgressIdx = isComplete ? -1 : doneCount
  const isEscalated = finalSnapshot.status === 'escalated' || Boolean(finalSnapshot.escalation_reason)
  const showHint = !escalationStep && !isComplete
  const displaySteps = [
    ...allSteps.map((s, i) => ({ ...s, isHint: false, displayIdx: i })),
    ...(showHint ? [{ node: 'hint', label: 'Escalation (if needed)', sublabel: 'Automatic fallback', isDone: false, isHint: true, displayIdx: allSteps.length }] : []),
  ]
  const progressPct = isComplete ? 100 : Math.round((doneCount / allSteps.length) * 100)

  return (
    <div className="fade-in space-y-4">
      {/* ── Processing card ── */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        {/* Gradient header */}
        <div className={`px-6 py-5 transition-all duration-700 ${
          isComplete && isEscalated
            ? 'bg-gradient-to-r from-amber-500 to-orange-500'
            : isComplete
            ? 'bg-gradient-to-r from-emerald-500 to-teal-500'
            : 'bg-gradient-to-r from-indigo-600 via-indigo-500 to-violet-600'
        }`}>
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <p className="text-white/70 text-[11px] font-semibold uppercase tracking-widest mb-1.5">
                {isComplete ? (isEscalated ? 'Escalated' : 'Resolved') : 'Processing'}
              </p>
              <p className="text-white font-semibold text-sm leading-snug line-clamp-2">{text}</p>
            </div>
            <div className="flex-shrink-0 mt-0.5">
              {!isComplete && !wsError && retryCount === 0 && (
                <span className="inline-flex items-center gap-1.5 bg-white/20 backdrop-blur-sm text-white text-xs font-semibold px-2.5 py-1 rounded-full tabular-nums">
                  <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
                  {liveElapsed > 0 ? `${liveElapsed}s` : 'Running'}
                </span>
              )}
              {!isComplete && retryCount > 0 && (
                <span className="inline-flex items-center gap-1.5 bg-white/20 backdrop-blur-sm text-white text-xs font-semibold px-2.5 py-1 rounded-full">
                  <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
                  Reconnecting…
                </span>
              )}
              {isComplete && !wsError && (
                <span className="inline-flex items-center gap-1.5 bg-white/20 backdrop-blur-sm text-white text-xs font-semibold px-2.5 py-1 rounded-full">
                  <svg className="w-3 h-3" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 00-1.414 0L8 12.586 4.707 9.293a1 1 0 00-1.414 1.414l4 4a1 1 0 001.414 0l8-8a1 1 0 000-1.414z" clipRule="evenodd" />
                  </svg>
                  {elapsedSec != null ? `Done in ${elapsedSec}s` : 'Done'}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Steps */}
        <div className="px-6 py-5">
          <ol aria-label="Agent processing steps" className="space-y-0">
            {displaySteps.map((step, i) => {
              const isLast = i === displaySteps.length - 1
              const isActive = !step.isHint && step.displayIdx === inProgressIdx && !wsError
              return (
                <li key={step.node} className="flex gap-4">
                  <div className="flex flex-col items-center">
                    {step.isHint ? (
                      <div className="w-9 h-9 rounded-full bg-slate-50 border-2 border-dashed border-slate-200 flex items-center justify-center flex-shrink-0" aria-hidden="true">
                        <svg className="w-3.5 h-3.5 text-slate-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 19.5l15-15m0 0H8.25m11.25 0v11.25" />
                        </svg>
                      </div>
                    ) : (
                      <StepIcon isDone={step.isDone} isActive={isActive} nodeKey={step.node} />
                    )}
                    {!isLast && (
                      <div
                        className={`w-0.5 my-2 flex-1 rounded-full transition-all duration-700 ${step.isDone ? 'bg-emerald-200' : 'bg-slate-100'}`}
                        style={{ minHeight: '1.5rem' }}
                        aria-hidden="true"
                      />
                    )}
                  </div>

                  <div className={`flex-1 ${isLast ? 'pb-0' : 'pb-0'} pt-1`}>
                    <p className={`text-sm font-semibold transition-colors duration-300 ${
                      step.isHint ? 'text-slate-300' : step.isDone ? 'text-slate-900' : isActive ? 'text-indigo-700' : 'text-slate-400'
                    }`}>
                      {step.label}
                      {isActive && <span className="ml-1 text-indigo-400 animate-pulse" aria-hidden="true">…</span>}
                    </p>
                    <p className={`text-xs mt-0.5 transition-colors duration-300 ${
                      step.isHint ? 'text-slate-200 italic' : step.isDone ? 'text-slate-400' : isActive ? 'text-indigo-400' : 'text-slate-300'
                    }`}>
                      {step.isHint ? 'Automatic fallback if needed' : (NODE_META[step.node]?.sublabel ?? step.sublabel)}
                    </p>
                    {!isLast && <div className="mt-3" />}
                  </div>
                </li>
              )
            })}
          </ol>
        </div>

        {/* Progress bar */}
        <div className="h-1 bg-slate-100" role="progressbar" aria-valuenow={progressPct} aria-valuemin={0} aria-valuemax={100}>
          <div
            className={`h-full transition-all duration-700 ease-out ${isEscalated && isComplete ? 'bg-amber-400' : isComplete ? 'bg-emerald-400' : 'bg-indigo-500'}`}
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>

      {/* ── Result card ── */}
      {isComplete && !wsError && (
        <div
          className={`bg-white rounded-2xl shadow-sm overflow-hidden border fade-in ${isEscalated ? 'border-amber-200' : 'border-emerald-200'}`}
          role="status"
          aria-live="polite"
        >
          {/* Coloured top band */}
          <div className={`px-6 py-4 border-b ${isEscalated ? 'bg-amber-50 border-amber-100' : 'bg-emerald-50 border-emerald-100'}`}>
            <div className="flex items-center gap-3">
              <div className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 ${isEscalated ? 'bg-amber-100' : 'bg-emerald-100'}`}>
                {isEscalated ? (
                  <svg className="w-4 h-4 text-amber-600" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                    <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4 text-emerald-600" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
                  </svg>
                )}
              </div>
              <div>
                <h3 className={`font-semibold text-sm ${isEscalated ? 'text-amber-900' : 'text-emerald-900'}`}>
                  {isEscalated ? 'Escalated to Human Queue' : 'Resolved automatically'}
                </h3>
                <p className={`text-xs mt-0.5 ${isEscalated ? 'text-amber-600' : 'text-emerald-600'}`}>
                  {isEscalated ? 'A support agent will follow up shortly' : `Completed${elapsedSec != null ? ` in ${elapsedSec}s` : ''}`}
                </p>
              </div>
            </div>
          </div>

          {/* Body */}
          <div className="px-6 py-4 space-y-3">
            {isEscalated ? (
              <>
                {finalSnapshot.escalation_reason && (() => {
                  const isDestructive = finalSnapshot.escalation_reason?.toLowerCase().includes('confirmation')
                  return isDestructive ? (
                    <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 space-y-1.5">
                      <p className="text-sm font-semibold text-amber-800">Manual approval required</p>
                      <p className="text-sm text-amber-700">This action (e.g. access revoke, account lock) requires explicit admin confirmation before it can be executed. Your admin has been notified and will action it shortly.</p>
                    </div>
                  ) : (
                    <p className="text-sm text-slate-600 leading-relaxed">{finalSnapshot.escalation_reason}</p>
                  )
                })()}
                {finalSnapshot.assignee_group && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-400">Assigned to</span>
                    <span className="text-xs font-semibold text-slate-700 bg-slate-100 px-2 py-0.5 rounded-full">{finalSnapshot.assignee_group}</span>
                  </div>
                )}
              </>
            ) : (
              <>
                {finalSnapshot.resolution ? (
                  <>
                    <p className="text-sm text-slate-700 leading-relaxed">{finalSnapshot.resolution}</p>
                    <CopyButton text={finalSnapshot.resolution} />
                  </>
                ) : (
                  <p className="text-sm text-slate-400">Ticket processed successfully.</p>
                )}
              </>
            )}

            {finalSnapshot.trace_url && (
              <a
                href={finalSnapshot.trace_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-xs text-indigo-500 hover:text-indigo-700 font-medium transition-colors"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                  <path fillRule="evenodd" d="M4.25 5.5a.75.75 0 00-.75.75v8.5c0 .414.336.75.75.75h8.5a.75.75 0 00.75-.75v-4a.75.75 0 011.5 0v4A2.25 2.25 0 0112.75 17h-8.5A2.25 2.25 0 012 14.75v-8.5A2.25 2.25 0 014.25 4h5a.75.75 0 010 1.5h-5z" clipRule="evenodd" />
                  <path fillRule="evenodd" d="M6.194 12.753a.75.75 0 001.06.053L16.5 4.44v2.81a.75.75 0 001.5 0v-4.5a.75.75 0 00-.75-.75h-4.5a.75.75 0 000 1.5h2.553l-9.056 8.194a.75.75 0 00-.053 1.06z" clipRule="evenodd" />
                </svg>
                View LangSmith trace
              </a>
            )}
          </div>
        </div>
      )}

      {/* ── Error card ── */}
      {wsError && (
        <div className="bg-white rounded-2xl shadow-sm border border-red-200 overflow-hidden fade-in" role="alert">
          <div className="bg-red-50 border-b border-red-100 px-6 py-4">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                <svg className="w-4 h-4 text-red-600" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                  <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
                </svg>
              </div>
              <h3 className="font-semibold text-sm text-red-900">Connection Error</h3>
            </div>
          </div>
          <div className="px-6 py-4">
            <p className="text-sm text-red-600 mb-4">{wsError}</p>
            <button onClick={onReset} className="text-sm text-indigo-600 font-semibold hover:text-indigo-800 transition-colors">
              ← Try again
            </button>
          </div>
        </div>
      )}

      {/* ── Submit another ── */}
      {isComplete && (
        <button
          onClick={onReset}
          className="w-full flex items-center justify-center gap-2 bg-white border border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/50 rounded-xl py-3 text-sm font-semibold text-slate-600 hover:text-indigo-700 transition-all duration-150 shadow-sm fade-in"
        >
          <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path d="M10.75 4.75a.75.75 0 00-1.5 0v4.5h-4.5a.75.75 0 000 1.5h4.5v4.5a.75.75 0 001.5 0v-4.5h4.5a.75.75 0 000-1.5h-4.5v-4.5z" />
          </svg>
          Submit another request
        </button>
      )}
    </div>
  )
}
