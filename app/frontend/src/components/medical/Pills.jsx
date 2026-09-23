import { ALERT_STATUS, RECORD_STATUS, severityStyle } from '../../lib/medical'

const base =
  'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold tracking-wide uppercase'

/** Severity of a finding or alert. The word is always present, so the badge
 *  does not rely on colour alone. */
export function SeverityBadge({ severity, className = '' }) {
  const style = severityStyle(severity)
  return <span className={`${base} ${style.badge} ${className}`}>{style.label}</span>
}

/** Where an alert is in its lifecycle. */
export function StatusPill({ status, className = '' }) {
  const style = ALERT_STATUS[status] ?? { label: status, chip: 'bg-bark-100 text-stone-neutral' }
  return <span className={`${base} ${style.chip} ${className}`}>{style.label}</span>
}

/** The status stored on a record (a vaccination, medication or follow-up). */
export function RecordStatusPill({ status, className = '' }) {
  if (!status) return null
  return (
    <span
      className={`${base} ${RECORD_STATUS[status] ?? 'bg-bark-100 text-stone-neutral'} ${className}`}
    >
      {status.replace('_', ' ')}
    </span>
  )
}

/** Shown where a section has nothing to display, saying what would appear. */
export function EmptyState({ children }) {
  return (
    <p className="border-bark-100 text-stone-neutral rounded-xl border border-dashed px-4 py-8 text-center text-sm">
      {children}
    </p>
  )
}

/** A failure the user can act on. Never shows a status code or a trace. */
export function ErrorNote({ children, onRetry }) {
  return (
    <div
      role="alert"
      className="bg-rust/10 text-rust flex flex-col gap-2 rounded-xl px-4 py-3 text-sm font-medium sm:flex-row sm:items-center sm:justify-between"
    >
      <span>{children}</span>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="text-rust-dark shrink-0 self-start underline underline-offset-2 sm:self-auto"
        >
          Try again
        </button>
      )}
    </div>
  )
}

/** A confirmation that something saved. */
export function SuccessNote({ children }) {
  return (
    <p
      role="status"
      className="bg-olive-100 text-olive-800 rounded-xl px-4 py-3 text-sm font-medium"
    >
      {children}
    </p>
  )
}
