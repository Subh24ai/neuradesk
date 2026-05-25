import { Component, ErrorInfo, ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  message: string
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, message: '' }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Uncaught error:', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl ring-1 ring-slate-900/5 p-8 max-w-md w-full text-center">

            {/* Logo */}
            <div className="flex items-center justify-center gap-2.5 mb-8">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 via-indigo-600 to-violet-700 flex items-center justify-center shadow-sm">
                <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" aria-hidden="true">
                  <line x1="12" y1="4.5" x2="12" y2="12.5" stroke="white" strokeWidth="1.8" strokeLinecap="round" opacity="0.75"/>
                  <line x1="5.5" y1="19.5" x2="12" y2="12.5" stroke="white" strokeWidth="1.8" strokeLinecap="round" opacity="0.75"/>
                  <line x1="18.5" y1="19.5" x2="12" y2="12.5" stroke="white" strokeWidth="1.8" strokeLinecap="round" opacity="0.75"/>
                  <circle cx="12" cy="4.5" r="2.25" fill="white"/>
                  <circle cx="5.5" cy="19.5" r="2.25" fill="white" opacity="0.85"/>
                  <circle cx="18.5" cy="19.5" r="2.25" fill="white" opacity="0.85"/>
                  <circle cx="12" cy="12.5" r="3.25" fill="white"/>
                </svg>
              </div>
              <span className="text-sm font-bold tracking-tight">
                <span className="text-indigo-600">Neura</span><span className="text-slate-900">Desk</span>
              </span>
            </div>

            {/* Icon */}
            <div className="w-14 h-14 rounded-2xl bg-red-50 border border-red-100 flex items-center justify-center mx-auto mb-5">
              <svg className="w-7 h-7 text-red-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
              </svg>
            </div>

            <h2 className="text-xl font-bold text-slate-900 mb-2">Something went wrong</h2>
            <p className="text-sm text-slate-500 mb-8 leading-relaxed">
              An unexpected error occurred. This has been logged and our team will look into it.
            </p>

            {/* Actions */}
            <div className="flex flex-col sm:flex-row gap-3">
              <button
                onClick={() => window.location.href = '/'}
                className="flex-1 flex items-center justify-center gap-2 border border-slate-200 text-slate-700 text-sm font-semibold px-4 py-2.5 rounded-xl hover:bg-slate-50 hover:border-slate-300 transition-all"
              >
                <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                  <path fillRule="evenodd" d="M9.293 2.293a1 1 0 011.414 0l7 7A1 1 0 0117 11h-1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-3a1 1 0 00-1-1H9a1 1 0 00-1 1v3a1 1 0 01-1 1H5a1 1 0 01-1-1v-6H3a1 1 0 01-.707-1.707l7-7z" clipRule="evenodd" />
                </svg>
                Go home
              </button>
              <button
                onClick={() => window.location.reload()}
                className="flex-1 flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-4 py-2.5 rounded-xl transition-colors shadow-sm"
              >
                <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                  <path fillRule="evenodd" d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H3.989a.75.75 0 00-.75.75v4.242a.75.75 0 001.5 0v-2.43l.31.31a7 7 0 0011.712-3.138.75.75 0 00-1.449-.39zm1.23-3.723a.75.75 0 00.219-.53V2.929a.75.75 0 00-1.5 0V5.36l-.31-.31A7 7 0 003.239 8.188a.75.75 0 101.448.389A5.5 5.5 0 0113.89 6.11l.311.31h-2.432a.75.75 0 000 1.5h4.243a.75.75 0 00.53-.219z" clipRule="evenodd" />
                </svg>
                Reload page
              </button>
            </div>

            {/* Collapsible technical details */}
            {this.state.message && (
              <details className="mt-6 text-left">
                <summary className="text-xs text-slate-400 cursor-pointer hover:text-slate-600 transition-colors select-none">
                  Technical details
                </summary>
                <p className="mt-2 text-xs font-mono text-red-600 bg-red-50 border border-red-100 rounded-xl px-3.5 py-2.5 break-all leading-relaxed">
                  {this.state.message}
                </p>
              </details>
            )}
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
