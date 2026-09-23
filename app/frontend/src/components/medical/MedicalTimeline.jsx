import { RECORD_TYPES, fmtDate } from '../../lib/medical'
import { EmptyState } from './Pills'

/**
 * Every record type on one chronological list, newest first.
 *
 * Entries are built in lib/medical.js from what the API returned. A date in the
 * future — a scheduled vaccination or a pending follow-up — is marked as
 * upcoming so it is not read as something that already happened.
 */
export default function MedicalTimeline({ entries }) {
  if (!entries.length) {
    return <EmptyState>Nothing recorded yet. Added records will appear here in date order.</EmptyState>
  }

  return (
    <ol className="relative">
      {entries.map((entry, index) => {
        const type = RECORD_TYPES[entry.kind]
        return (
          <li key={entry.id} className="flex gap-3 sm:gap-4">
            {/* Rail: icon plus the line joining it to the next entry. */}
            <div className="flex flex-col items-center">
              <span
                aria-hidden="true"
                className="border-bark-100 grid h-9 w-9 shrink-0 place-items-center rounded-full border bg-white text-base"
              >
                {type.icon}
              </span>
              {index < entries.length - 1 && <span className="bg-bark-100 w-px flex-1" />}
            </div>

            <div className="min-w-0 flex-1 pb-6">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <time className="text-bark-900 text-sm font-semibold" dateTime={entry.date}>
                  {fmtDate(entry.date)}
                </time>
                <span className="text-stone-neutral text-xs font-semibold tracking-wide uppercase">
                  {type.label}
                </span>
                {entry.upcoming && (
                  <span className="bg-amber-brand/25 text-amber-brand-dark rounded-full px-2 py-0.5 text-[11px] font-bold uppercase">
                    Upcoming
                  </span>
                )}
              </div>
              <p className="text-bark-900 mt-0.5 text-sm font-medium">{entry.title}</p>
              {entry.detail && <p className="mt-0.5 text-sm">{entry.detail}</p>}
              {entry.meta && (
                <p className="text-stone-neutral mt-0.5 text-xs">{entry.meta}</p>
              )}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
