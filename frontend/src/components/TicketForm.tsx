import { useEffect, useRef, useState } from 'react'

interface Props {
  onSubmit: (text: string, imageB64: string | null) => void
  isSubmitting?: boolean
  initialText?: string
  greeting?: string
  agentsOnline?: boolean
}

const SUGGESTIONS = [
  {
    label: 'Reset my password',
    icon: <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M10 1a4.5 4.5 0 00-4.5 4.5V9H5a2 2 0 00-2 2v6a2 2 0 002 2h10a2 2 0 002-2v-6a2 2 0 00-2-2h-.5V5.5A4.5 4.5 0 0010 1zm3 8V5.5a3 3 0 10-6 0V9h6z" clipRule="evenodd" /></svg>,
  },
  {
    label: 'VPN not connecting',
    icon: <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M9.69 18.933l.003.001C9.89 19.02 10 19 10 19s.11.02.308-.066l.002-.001.006-.003.018-.008a5.741 5.741 0 00.281-.14c.186-.096.446-.24.757-.433.62-.384 1.445-.966 2.274-1.765C15.302 15.526 17 13.1 17 10a7 7 0 10-14 0c0 3.1 1.698 5.526 3.354 7.105.83.8 1.654 1.38 2.274 1.766.311.192.571.336.757.432a5.742 5.742 0 00.281.14l.018.008.006.003zM10 11.25a1.25 1.25 0 100-2.5 1.25 1.25 0 000 2.5z" clipRule="evenodd" /></svg>,
  },
  {
    label: 'Access to shared drive',
    icon: <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" /></svg>,
  },
  {
    label: 'Software install request',
    icon: <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M10 2a.75.75 0 01.75.75v7.19l2.22-2.22a.75.75 0 111.06 1.06l-3.5 3.5a.75.75 0 01-1.06 0l-3.5-3.5a.75.75 0 111.06-1.06l2.22 2.22V2.75A.75.75 0 0110 2zm-6 11a.75.75 0 01.75.75v.5a1.75 1.75 0 001.75 1.75h7a1.75 1.75 0 001.75-1.75v-.5a.75.75 0 011.5 0v.5a3.25 3.25 0 01-3.25 3.25h-7A3.25 3.25 0 014 13.75v-.5A.75.75 0 014 12z" clipRule="evenodd" /></svg>,
  },
  {
    label: 'Laptop running slow',
    icon: <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M2 4.25A2.25 2.25 0 014.25 2h11.5A2.25 2.25 0 0118 4.25v8.5A2.25 2.25 0 0115.75 15h-3.105a3.501 3.501 0 001.1 1.677A.75.75 0 0113.26 18H6.74a.75.75 0 01-.484-1.323A3.501 3.501 0 007.355 15H4.25A2.25 2.25 0 012 12.75v-8.5zm1.5 0a.75.75 0 01.75-.75h11.5a.75.75 0 01.75.75v7.5a.75.75 0 01-.75.75H4.25a.75.75 0 01-.75-.75v-7.5z" clipRule="evenodd" /></svg>,
  },
  {
    label: 'Submit a leave request',
    icon: <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M5.75 2a.75.75 0 01.75.75V4h7V2.75a.75.75 0 011.5 0V4h.25A2.75 2.75 0 0118 6.75v8.5A2.75 2.75 0 0115.25 18H4.75A2.75 2.75 0 012 15.25v-8.5A2.75 2.75 0 014.75 4H5V2.75A.75.75 0 015.75 2zm-1 5.5c-.69 0-1.25.56-1.25 1.25v6.5c0 .69.56 1.25 1.25 1.25h10.5c.69 0 1.25-.56 1.25-1.25v-6.5c0-.69-.56-1.25-1.25-1.25H4.75z" clipRule="evenodd" /></svg>,
  },
]

const isMac = typeof navigator !== 'undefined' && /Mac/i.test(navigator.platform)
const SHORTCUT = isMac ? '⌘↵' : 'Ctrl↵'

const MAX_IMAGE_BYTES = 1_048_576

export default function TicketForm({ onSubmit, isSubmitting = false, initialText = '', greeting, agentsOnline = true }: Props) {
  const [text, setText] = useState(initialText)
  const [imageB64, setImageB64] = useState<string | null>(null)
  const [imageName, setImageName] = useState<string | null>(null)
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(null)
  const [imageError, setImageError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    return () => { if (imagePreviewUrl) URL.revokeObjectURL(imagePreviewUrl) }
  }, [imagePreviewUrl])

  function processFile(file: File) {
    setImageError(null)
    if (!file.type.startsWith('image/')) {
      setImageError('Only image files are supported.')
      return
    }
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

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) processFile(file)
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) processFile(file)
  }

  function clearImage() {
    if (imagePreviewUrl) URL.revokeObjectURL(imagePreviewUrl)
    setImageB64(null)
    setImageName(null)
    setImagePreviewUrl(null)
    setImageError(null)
    if (fileRef.current) fileRef.current.value = ''
  }

  function handleSuggestion(label: string) {
    setText(label)
    requestAnimationFrame(() => {
      textareaRef.current?.focus()
      textareaRef.current?.setSelectionRange(label.length, label.length)
    })
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!text.trim() || isSubmitting) return
    onSubmit(text.trim(), imageB64)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault()
      if (text.trim() && !isSubmitting) onSubmit(text.trim(), imageB64)
    }
  }

  return (
    <div className="fade-in">
      {/* Hero section */}
      <div className="mb-8">
        <div className="flex flex-wrap items-center gap-2 mb-4">
          {agentsOnline ? (
            <span className="inline-flex items-center gap-1.5 text-[11px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2.5 py-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" aria-hidden="true" />
              4 AI agents online
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-[11px] font-bold text-red-600 bg-red-50 border border-red-200 rounded-full px-2.5 py-1">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500" aria-hidden="true" />
              backend offline
            </span>
          )}
          <span className="text-slate-300 text-xs hidden sm:inline">·</span>
          <span className="text-xs text-slate-400 font-medium hidden sm:inline">avg. ~4s resolution</span>
        </div>
        <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight leading-tight">
          {greeting ?? 'Submit a Request'}
        </h2>
        <p className="mt-2 text-slate-500 text-base leading-relaxed">
          {greeting ? 'What can we help you with today?' : 'Describe your IT or HR issue — our agents resolve it automatically.'}
        </p>
      </div>

      {/* Quick suggestions */}
      <div className="mb-5">
        <p className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-3">Quick requests</p>
        <div className="flex flex-wrap gap-2 stagger">
          {SUGGESTIONS.map(({ label, icon }) => (
            <button
              key={label}
              type="button"
              onClick={() => handleSuggestion(label)}
              className="fade-in inline-flex items-center gap-1.5 text-xs font-medium text-slate-600 bg-white border border-slate-200 rounded-full px-3 py-1.5 hover:border-indigo-300 hover:text-indigo-700 hover:bg-indigo-50/60 transition-all duration-150 shadow-sm hover:shadow-md"
            >
              {icon}
              {label}
            </button>
          ))}
        </div>
      </div>

      <form
        onSubmit={handleSubmit}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`bg-white rounded-2xl border overflow-hidden transition-all duration-150 shadow-sm ${
          dragging
            ? 'border-indigo-400 ring-2 ring-indigo-200 shadow-md'
            : 'border-slate-200 hover:border-slate-300'
        }`}
      >
        <div className="relative">
          <textarea
            ref={textareaRef}
            // eslint-disable-next-line jsx-a11y/no-autofocus
            autoFocus
            required
            maxLength={4000}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={5}
            placeholder="Describe your issue in detail… or drop a screenshot here"
            className="w-full px-5 py-4 text-sm text-slate-800 placeholder-slate-400 resize-none focus:outline-none leading-relaxed bg-transparent"
            aria-describedby="char-count"
          />
          {text.length > 3500 && (
            <span
              id="char-count"
              className={`absolute bottom-2 right-4 text-xs ${text.length >= 4000 ? 'text-red-500' : 'text-slate-400'}`}
            >
              {text.length}/4000
            </span>
          )}
        </div>

        {/* Drag hint when empty */}
        {dragging && !imagePreviewUrl && (
          <div className="px-5 pb-3 flex items-center gap-2 text-indigo-600 text-sm font-medium">
            <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fillRule="evenodd" d="M1 8a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 018.07 3h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0016.07 6H17a2 2 0 012 2v7a2 2 0 01-2 2H3a2 2 0 01-2-2V8zm13.5 3a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0zM10 14a2.5 2.5 0 100-5 2.5 2.5 0 000 5z" clipRule="evenodd" />
            </svg>
            Drop image to attach
          </div>
        )}

        {/* Image preview */}
        {imagePreviewUrl && (
          <div className="px-5 pb-3">
            <div className="relative inline-flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2">
              <img
                src={imagePreviewUrl}
                alt={imageName ?? 'Attached screenshot'}
                className="h-10 w-auto rounded-lg object-cover"
              />
              <div className="min-w-0">
                <p className="text-xs font-medium text-slate-700 truncate max-w-[160px]">{imageName}</p>
                <p className="text-[10px] text-slate-400">Screenshot attached</p>
              </div>
              <button
                type="button"
                onClick={clearImage}
                aria-label="Remove image"
                className="ml-1 w-5 h-5 bg-slate-200 hover:bg-slate-300 text-slate-600 rounded-full flex items-center justify-center text-xs transition-colors flex-shrink-0"
              >
                ×
              </button>
            </div>
          </div>
        )}

        {imageError && (
          <p className="px-5 pb-3 text-xs text-red-600">{imageError}</p>
        )}

        <div className="border-t border-slate-100 px-4 py-3 bg-slate-50/60 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className="flex items-center gap-1.5 text-xs text-slate-500 border border-slate-200 rounded-lg px-3 py-1.5 hover:bg-white hover:text-slate-700 hover:border-slate-300 hover:shadow-sm transition-all"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fillRule="evenodd" d="M1 8a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 018.07 3h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0016.07 6H17a2 2 0 012 2v7a2 2 0 01-2 2H3a2 2 0 01-2-2V8zm13.5 3a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0zM10 14a2.5 2.5 0 100-5 2.5 2.5 0 000 5z" clipRule="evenodd" />
            </svg>
            {imagePreviewUrl ? 'Change image' : 'Attach screenshot'}
          </button>

          <input ref={fileRef} type="file" accept="image/*" onChange={handleFileChange} className="hidden" aria-hidden="true" />

          <span className="text-xs text-slate-300 hidden sm:block ml-0.5 font-mono">{SHORTCUT}</span>

          <button
            type="submit"
            disabled={!text.trim() || isSubmitting}
            className="ml-auto flex items-center gap-2 bg-gradient-to-r from-indigo-600 to-indigo-700 text-white rounded-lg px-5 py-1.5 text-sm font-semibold hover:from-indigo-700 hover:to-indigo-800 disabled:opacity-40 transition-all shadow-sm hover:shadow-md"
          >
            {isSubmitting ? (
              <>
                <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Creating…
              </>
            ) : (
              <>
                Submit
                <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                  <path fillRule="evenodd" d="M3 10a.75.75 0 01.75-.75h10.638L10.23 5.29a.75.75 0 111.04-1.08l5.5 5.25a.75.75 0 010 1.08l-5.5 5.25a.75.75 0 11-1.04-1.08l4.158-3.96H3.75A.75.75 0 013 10z" clipRule="evenodd" />
                </svg>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  )
}
