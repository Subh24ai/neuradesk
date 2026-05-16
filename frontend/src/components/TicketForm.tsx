import { useRef, useState } from 'react'

interface Props {
  onSubmit: (text: string, imageB64: string | null) => void
}

export default function TicketForm({ onSubmit }: Props) {
  const [text, setText] = useState('')
  const [imageB64, setImageB64] = useState<string | null>(null)
  const [imageName, setImageName] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setImageName(file.name)
    const reader = new FileReader()
    reader.onload = () => {
      // Strip "data:image/...;base64," prefix — backend expects raw base64
      const result = reader.result as string
      setImageB64(result.split(',')[1])
    }
    reader.readAsDataURL(file)
  }

  function clearImage() {
    setImageB64(null)
    setImageName(null)
    if (fileRef.current) fileRef.current.value = ''
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!text.trim()) return
    onSubmit(text.trim(), imageB64)
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-white rounded-lg shadow-sm border border-gray-200 p-6"
    >
      <h2 className="text-lg font-semibold text-gray-900 mb-1">Submit a Ticket</h2>
      <p className="text-sm text-gray-500 mb-4">
        Describe your IT or HR request. Our AI agents will resolve it automatically.
      </p>

      <textarea
        required
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={5}
        placeholder="e.g. I can't log in to Jira, I need access to the marketing shared drive, I forgot my VPN password…"
        className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
      />

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          className="text-sm text-gray-600 border border-gray-300 rounded-md px-3 py-1.5 hover:bg-gray-50 transition-colors"
        >
          {imageName ? `📎 ${imageName}` : 'Attach screenshot'}
        </button>

        {imageName && (
          <button
            type="button"
            onClick={clearImage}
            className="text-sm text-gray-400 hover:text-gray-700 transition-colors"
            aria-label="Remove attached image"
          >
            Remove
          </button>
        )}

        {/* Hidden file input — triggered by the button above */}
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          onChange={handleFileChange}
          className="hidden"
          aria-hidden="true"
        />

        <button
          type="submit"
          disabled={!text.trim()}
          className="ml-auto bg-indigo-600 text-white rounded-md px-5 py-1.5 text-sm font-medium hover:bg-indigo-700 disabled:opacity-40 transition-colors"
        >
          Submit
        </button>
      </div>
    </form>
  )
}
