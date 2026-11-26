import { useEffect, useRef, useState } from 'react'

interface Props {
  onSubmit: (text: string, imageB64: string | null) => void
  isSubmitting?: boolean
  initialText?: string
  greeting?: string
  agentsOnline?: boolean
}

interface Template {
  label: string
  text: string
  icon: string
}

// Fill-in templates: the [bracketed] parts are what the agents need to act
// automatically. Clicking a template selects the first blank so the user types over it.
const TEMPLATE_GROUPS: { group: string; items: Template[] }[] = [
  {
    group: 'IT',
    items: [
      { label: 'Reset my password', text: "I forgot my password and can't sign in.", icon: 'M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z' },
      { label: 'VPN not connecting', text: "My VPN won't connect. The error says: [error message].", icon: 'M8.288 15.038a5.25 5.25 0 017.424 0M5.106 11.856c3.807-3.808 9.98-3.808 13.788 0M1.924 8.674c5.565-5.565 14.587-5.565 20.152 0M12.53 18.22l-.53.53-.53-.53a.75.75 0 011.06 0z' },
      { label: 'Request access', text: 'I need access to [system or shared drive] for [reason].', icon: 'M15.75 5.25a3 3 0 013 3m3 0a6 6 0 01-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1121.75 8.25z' },
      { label: 'Install software', text: 'Please install [software name] on my laptop. I need it for [reason].', icon: 'M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3' },
      { label: 'Report an outage', text: '[System or service] is down for [me / my team] since [time].', icon: 'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z' },
    ],
  },
  {
    group: 'HR',
    items: [
      { label: 'Request leave', text: "I'd like to take annual leave from [start date] to [end date].", icon: 'M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5' },
      { label: 'Ask about a policy', text: 'What is our policy on [topic]?', icon: 'M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z' },
    ],
  },
]

const PLACEHOLDER = /\[[^\]]+\]/
const isMac = typeof navigator !== 'undefined' && /Mac/i.test(navigator.platform)
const MAX_IMAGE_BYTES = 1_048_576
const MAX_CHARS = 4000

export default function TicketForm({ onSubmit, isSubmitting = false, initialText = '', greeting, agentsOnline = true }: Props) {
  const [text, setText] = useState(initialText)
  const [imageB64, setImageB64] = useState<string | null>(null)
  const [imageName, setImageName] = useState<string | null>(null)
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(null)
  const [imageError, setImageError] = useState<string | null>(null)
  const [blankError, setBlankError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    return () => { if (imagePreviewUrl) URL.revokeObjectURL(imagePreviewUrl) }
  }, [imagePreviewUrl])

  // Opened pre-filled (quick start / resubmit): put the cursor on the first [blank].
  useEffect(() => {
    if (initialText && PLACEHOLDER.test(initialText)) selectFirstBlank(initialText)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function selectFirstBlank(value: string) {
    const m = PLACEHOLDER.exec(value)
    requestAnimationFrame(() => {
      const el = textareaRef.current
      if (!el) return
      el.focus()
      if (m) el.setSelectionRange(m.index, m.index + m[0].length)
      else el.setSelectionRange(value.length, value.length)
    })
  }

  function applyTemplate(t: Template) {
    setText(t.text)
    setBlankError(null)
    selectFirstBlank(t.text)
  }

  function processFile(file: File) {
    setImageError(null)
    if (!file.type.startsWith('image/')) { setImageError('Only image files are supported.'); return }
    if (file.size > MAX_IMAGE_BYTES) {
      setImageError(`Image too large (${(file.size / 1_048_576).toFixed(1)} MB). Max 1 MB.`)
      return
    }
    if (imagePreviewUrl) URL.revokeObjectURL(imagePreviewUrl)
    setImageName(file.name)
    setImagePreviewUrl(URL.createObjectURL(file))
    const reader = new FileReader()
    reader.onload = () => setImageB64((reader.result as string).split(',')[1])
    reader.readAsDataURL(file)
  }

  function clearImage() {
    if (imagePreviewUrl) URL.revokeObjectURL(imagePreviewUrl)
    setImageB64(null); setImageName(null); setImagePreviewUrl(null); setImageError(null)
    if (fileRef.current) fileRef.current.value = ''
  }

  function trySubmit() {
    const value = text.trim()
    if (!value || isSubmitting) return
    if (PLACEHOLDER.test(value)) {
      setBlankError('Fill in the parts in [brackets] first so we can act on your request.')
      selectFirstBlank(text)
      return
    }
    setBlankError(null)
    onSubmit(value, imageB64)
  }

  const canSubmit = text.trim().length > 0 && !isSubmitting

  return (
    <div className="fade-in">
      {!agentsOnline && (
        <div role="alert" className="mb-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <span className="font-semibold">We can’t reach the NeuraDesk service right now.</span>{' '}
          You can still write your request, but submitting may fail until it’s back.
        </div>
      )}

      <div className="mb-7">
        <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight leading-tight">
          {greeting ?? 'Submit a request'}
        </h2>
        <p className="mt-2 text-slate-500 text-base leading-relaxed">
          Tell us what you need. Most requests are handled automatically in seconds.
        </p>
      </div>

      <div className="mb-5 space-y-3">
        {TEMPLATE_GROUPS.map(({ group, items }) => (
          <div key={group} className="flex flex-wrap items-center gap-2">
            <span className="w-8 text-[11px] font-bold uppercase tracking-widest text-slate-400">{group}</span>
            {items.map((t) => (
              <button
                key={t.label}
                type="button"
                onClick={() => applyTemplate(t)}
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 shadow-sm transition-all hover:border-indigo-300 hover:bg-indigo-50/60 hover:text-indigo-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d={t.icon} />
                </svg>
                {t.label}
              </button>
            ))}
          </div>
        ))}
      </div>

      <form
        onSubmit={(e) => { e.preventDefault(); trySubmit() }}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files?.[0]; if (f) processFile(f) }}
        className={`overflow-hidden rounded-2xl border bg-white shadow-sm transition-all duration-150 focus-within:border-indigo-400 focus-within:ring-2 focus-within:ring-indigo-100 ${
          dragging ? 'border-indigo-400 ring-2 ring-indigo-200' : 'border-slate-200'
        }`}
      >
        <label htmlFor="ticket-text" className="sr-only">Describe your request</label>
        <textarea
          id="ticket-text"
          ref={textareaRef}
          // eslint-disable-next-line jsx-a11y/no-autofocus
          autoFocus
          maxLength={MAX_CHARS}
          value={text}
          onChange={(e) => { setText(e.target.value); if (blankError && !PLACEHOLDER.test(e.target.value)) setBlankError(null) }}
          onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); trySubmit() } }}
          rows={6}
          placeholder="e.g. “I need access to the Finance shared drive for the Q3 audit.” You can also drop a screenshot here."
          aria-describedby="ticket-help"
          aria-invalid={Boolean(blankError)}
          className="w-full resize-none bg-transparent px-5 py-4 text-[15px] leading-relaxed text-slate-800 placeholder-slate-400 focus:outline-none"
        />

        {imagePreviewUrl && (
          <div className="px-5 pb-3">
            <div className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
              <img src={imagePreviewUrl} alt={imageName ?? 'Attached screenshot'} className="h-10 w-auto rounded-lg object-cover" />
              <div className="min-w-0">
                <p className="max-w-[180px] truncate text-xs font-medium text-slate-700">{imageName}</p>
                <p className="text-[10px] text-slate-400">Screenshot attached</p>
              </div>
              <button type="button" onClick={clearImage} aria-label="Remove image" className="ml-1 flex h-5 w-5 items-center justify-center rounded-full bg-slate-200 text-xs text-slate-600 hover:bg-slate-300">×</button>
            </div>
          </div>
        )}

        {(imageError || blankError) && (
          <p role="alert" className="px-5 pb-3 text-xs font-medium text-red-600">{blankError ?? imageError}</p>
        )}

        <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 bg-slate-50/70 px-4 py-3">
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition-all hover:border-slate-300 hover:text-slate-800"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fillRule="evenodd" d="M1 8a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 018.07 3h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0016.07 6H17a2 2 0 012 2v7a2 2 0 01-2 2H3a2 2 0 01-2-2V8zm13.5 3a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0zM10 14a2.5 2.5 0 100-5 2.5 2.5 0 000 5z" clipRule="evenodd" />
            </svg>
            {imagePreviewUrl ? 'Change screenshot' : 'Attach screenshot'}
          </button>
          <input ref={fileRef} type="file" accept="image/*" onChange={(e) => { const f = e.target.files?.[0]; if (f) processFile(f) }} className="hidden" aria-hidden="true" />

          <p id="ticket-help" className="hidden flex-1 text-xs text-slate-400 md:block">
            Include names, error messages and dates — the more detail, the more we can resolve automatically.
          </p>

          <div className="ml-auto flex items-center gap-3">
            {text.length > MAX_CHARS - 500 && (
              <span className={`text-xs tabular-nums ${text.length >= MAX_CHARS ? 'text-red-500' : 'text-slate-400'}`}>
                {text.length}/{MAX_CHARS}
              </span>
            )}
            <span className="hidden text-xs text-slate-400 sm:inline">
              <kbd className="rounded border border-slate-200 bg-white px-1.5 py-0.5 font-sans text-[11px] text-slate-500">{isMac ? '⌘' : 'Ctrl'}</kbd>
              {' + '}
              <kbd className="rounded border border-slate-200 bg-white px-1.5 py-0.5 font-sans text-[11px] text-slate-500">Enter</kbd>
            </span>
            <button
              type="submit"
              disabled={!canSubmit}
              className={`flex items-center gap-2 rounded-lg px-5 py-2 text-sm font-semibold transition-all ${
                canSubmit
                  ? 'bg-indigo-600 text-white shadow-sm hover:bg-indigo-700 hover:shadow-md'
                  : 'cursor-not-allowed bg-slate-200 text-slate-400'
              }`}
            >
              {isSubmitting ? (
                <>
                  <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Sending…
                </>
              ) : (
                <>
                  Submit
                  <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                    <path fillRule="evenodd" d="M3 10a.75.75 0 01.75-.75h10.638L10.23 5.29a.75.75 0 111.04-1.08l5.5 5.25a.75.75 0 010 1.08l-5.5 5.25a.75.75 0 11-1.04-1.08l4.158-3.96H3.75A.75.75 0 013 10z" clipRule="evenodd" />
                  </svg>
                </>
              )}
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
