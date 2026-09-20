import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'

/**
 * Floating FAQ assistant, available on every page.
 *
 * The classifier lives on the backend; this is only the surface. Answers that
 * came back below the confidence threshold are shown with the suggestion chips
 * so a stuck visitor always has a next step.
 */

const GREETING = {
  from: 'bot',
  text:
    'Hello, and welcome to Dogo-Paw. Ask me about adopting, fostering, ' +
    'volunteering, donations or how to reach us.',
  suggestions: [
    'How do I adopt a dog?',
    'What does fostering involve?',
    'How can I volunteer?',
  ],
}

export default function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState([GREETING])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)

  const listRef = useRef(null)
  const inputRef = useRef(null)

  // Keep the newest message in view as the thread grows.
  useEffect(() => {
    const list = listRef.current
    if (list) list.scrollTop = list.scrollHeight
  }, [messages, open])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  // Escape closes the panel, as with any dialog.
  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const send = async (text) => {
    const question = (text ?? input).trim()
    if (!question || sending) return

    setMessages((m) => [...m, { from: 'user', text: question }])
    setInput('')
    setSending(true)

    try {
      const reply = await api.chatbot(question)
      setMessages((m) => [
        ...m,
        {
          from: 'bot',
          text: reply.answer,
          suggestions: reply.suggestions ?? [],
          intent: reply.intent,
          confidence: reply.confidence,
          lowConfidence: reply.low_confidence,
        },
      ])
    } catch (err) {
      setMessages((m) => [...m, { from: 'bot', text: err.message, isError: true }])
    } finally {
      setSending(false)
    }
  }

  return (
    <>
      {/* Launcher */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls="chat-panel"
        aria-label={open ? 'Close the help assistant' : 'Open the help assistant'}
        className={`bg-olive-500 hover:bg-olive-600 fixed right-4 bottom-4 z-60 grid h-14 w-14 place-items-center rounded-full text-white shadow-lg transition-transform active:scale-95 sm:right-6 sm:bottom-6 ${
          open ? 'rotate-90' : ''
        }`}
      >
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          {open ? (
            <path
              d="M6 6l12 12M18 6L6 18"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          ) : (
            <path
              d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9.5 9.5 0 0 1-2.8-.4L4 21l1.3-3.7A8.2 8.2 0 0 1 3 11.5 8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5Z"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinejoin="round"
            />
          )}
        </svg>
      </button>

      {/* Panel */}
      {open && (
        <div
          id="chat-panel"
          role="dialog"
          aria-label="Dogo-Paw help assistant"
          className="border-bark-100 rounded-card fixed inset-x-4 bottom-22 z-60 flex max-h-[70vh] flex-col overflow-hidden border bg-white shadow-2xl sm:inset-x-auto sm:right-6 sm:bottom-24 sm:w-96"
        >
          <header className="bg-bark-900 flex items-center gap-3 px-4 py-3.5 text-white">
            <span className="bg-olive-500 grid h-9 w-9 place-items-center rounded-full text-sm font-bold">
              DP
            </span>
            <div className="min-w-0">
              <p className="text-sm font-semibold">Dogo-Paw assistant</p>
              <p className="text-xs text-white/70">
                Answers about adopting, fostering and volunteering
              </p>
            </div>
          </header>

          <div
            ref={listRef}
            className="flex-1 space-y-3 overflow-y-auto px-4 py-4"
            aria-live="polite"
          >
            {messages.map((m, i) => (
              <div key={i}>
                <div
                  className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
                    m.from === 'user'
                      ? 'bg-olive-500 ml-auto text-white'
                      : m.isError
                        ? 'bg-rust/10 text-rust'
                        : 'bg-bark-50 text-bark-900'
                  }`}
                >
                  {m.text}
                </div>

                {m.suggestions?.length > 0 && (
                  <ul className="mt-2 flex flex-wrap gap-2">
                    {m.suggestions.map((s) => (
                      <li key={s}>
                        <button
                          type="button"
                          onClick={() => send(s)}
                          disabled={sending}
                          className="border-olive-300 text-olive-700 hover:bg-olive-50 rounded-full border px-3 py-1.5 text-xs font-medium transition disabled:opacity-50"
                        >
                          {s}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}

            {sending && (
              <div className="bg-bark-50 flex w-16 items-center justify-center gap-1 rounded-2xl px-3.5 py-3">
                {[0, 150, 300].map((delay) => (
                  <span
                    key={delay}
                    className="bg-stone-neutral h-1.5 w-1.5 animate-bounce rounded-full"
                    style={{ animationDelay: `${delay}ms` }}
                  />
                ))}
                <span className="sr-only">Thinking…</span>
              </div>
            )}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault()
              send()
            }}
            className="border-bark-100 flex items-center gap-2 border-t p-3"
          >
            <label htmlFor="chat-input" className="sr-only">
              Your question
            </label>
            <input
              id="chat-input"
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask a question…"
              maxLength={500}
              className="border-bark-100 focus:border-olive-500 min-w-0 flex-1 rounded-full border-2 px-4 py-2.5 text-sm outline-none"
            />
            <button
              type="submit"
              disabled={sending || !input.trim()}
              aria-label="Send"
              className="bg-olive-500 hover:bg-olive-600 grid h-11 w-11 shrink-0 place-items-center rounded-full text-white transition disabled:opacity-40"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path
                  d="M4 12l16-8-6 8 6 8-16-8Z"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          </form>
        </div>
      )}
    </>
  )
}
