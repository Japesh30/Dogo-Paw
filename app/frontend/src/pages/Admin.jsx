import { useEffect, useState } from 'react'
import Spinner from '../components/Spinner'
import {
  ActivityChart,
  SegmentChart,
  Sparkline,
  TopDogsChart,
} from '../components/charts'
import { api } from '../lib/api'
import { useAuth } from '../context/useAuth'

const fmtTime = (iso) =>
  new Date(iso).toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })

const MINUTE = 60
const HOUR = MINUTE * 60
const DAY = HOUR * 24

/** "2 hours ago" — falls back to a date once it stops being useful. */
function timeAgo(iso) {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 45) return 'just now'

  const [value, unit] =
    seconds < HOUR
      ? [Math.round(seconds / MINUTE), 'minute']
      : seconds < DAY
        ? [Math.round(seconds / HOUR), 'hour']
        : seconds < DAY * 7
          ? [Math.round(seconds / DAY), 'day']
          : [null, null]

  if (value === null) {
    return new Date(iso).toLocaleDateString(undefined, {
      day: 'numeric',
      month: 'short',
    })
  }
  return `${value} ${unit}${value === 1 ? '' : 's'} ago`
}

const HOME_LABELS = {
  apartment: 'Apartment',
  house_no_yard: 'House, no yard',
  house_with_yard: 'House + yard',
}

const INTENT_LABELS = {
  adoption_process: 'Adoption process',
  foster_info: 'Fostering',
  volunteer_info: 'Volunteering',
  donation_info: 'Donations',
  contact_info: 'Contact',
  general_greeting: 'Greeting',
  unknown: 'Off-topic',
}

export default function Admin() {
  const { user } = useAuth()
  const [stats, setStats] = useState(null)
  const [segments, setSegments] = useState(null)
  const [error, setError] = useState('')
  const [showTable, setShowTable] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .adminStats()
      .then((data) => !cancelled && setStats(data))
      .catch((err) => !cancelled && setError(err.message))

    // Segmentation is a secondary panel — a failure there should not take the
    // whole dashboard down with it.
    api
      .adopterSegments()
      .then((data) => !cancelled && setSegments(data))
      .catch(() => !cancelled && setSegments({ available: false }))

    return () => {
      cancelled = true
    }
  }, [])

  if (error) {
    return (
      <div className="shell grid min-h-[60vh] place-items-center py-20 text-center">
        <div>
          <h1 className="text-2xl">Could not load the dashboard</h1>
          <p className="text-rust mt-3">{error}</p>
        </div>
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="grid min-h-[60vh] place-items-center">
        <Spinner label="Loading dashboard…" />
      </div>
    )
  }

  const {
    totals,
    activity,
    top_dogs: topDogs,
    recent_requests: recent,
    recent_activity: feed,
    chatbot,
  } = stats
  const weekTotal = activity.reduce((sum, d) => sum + d.requests, 0)

  const tiles = [
    { label: 'Dogs in the database', value: totals.dogs },
    { label: 'Volunteer sign-ups', value: totals.volunteers },
    { label: 'Match requests', value: totals.match_requests },
    { label: 'Registered users', value: totals.users },
    { label: 'Average top-match score', value: `${totals.avg_top_score}%` },
  ]

  return (
    <div className="bg-bark-50 min-h-screen py-10 sm:py-14">
      <div className="shell">
        {/* --------------- Header --------------- */}
        <header className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="eyebrow">Admin dashboard</p>
            <h1 className="mt-2 text-3xl sm:text-4xl">Activity overview</h1>
          </div>
          <p className="text-sm">
            Signed in as <span className="text-bark-900 font-semibold">{user.name}</span>
          </p>
        </header>

        {/* --------------- Hero figure --------------- */}
        <section className="card mt-8 grid gap-8 p-6 sm:p-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
          <div>
            <p className="text-sm font-semibold">Total match requests</p>
            <p className="text-bark-900 mt-1 text-6xl font-extrabold sm:text-7xl">
              {totals.match_requests}
            </p>
            <p className="mt-3 text-sm">
              <span className="text-bark-900 font-semibold tabular-nums">
                {weekTotal}
              </span>{' '}
              in the last 7 days
            </p>
            <div className="mt-5 max-w-[220px]">
              <Sparkline data={activity} />
            </div>
          </div>

          <div>
            <h2 className="text-bark-900 text-sm font-semibold">
              Match requests per day, last 7 days
            </h2>
            <div className="mt-3">
              <ActivityChart data={activity} />
            </div>
          </div>
        </section>

        {/* --------------- KPI row --------------- */}
        <section className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {tiles.map((t) => (
            <div key={t.label} className="card p-5">
              <p className="text-sm">{t.label}</p>
              <p className="text-bark-900 mt-2 text-3xl font-extrabold">
                {t.value}
              </p>
            </div>
          ))}
        </section>

        {/* --------------- Top dogs --------------- */}
        <section className="card mt-6 p-6 sm:p-8">
          <h2 className="text-bark-900 text-lg font-semibold">
            Most frequently top-ranked dogs
          </h2>
          <p className="mt-1 text-sm">
            How often each dog came out as the #1 recommendation.
          </p>
          <div className="mt-5">
            {topDogs.length ? (
              <TopDogsChart data={topDogs} />
            ) : (
              <p className="py-8 text-center text-sm">
                No match requests recorded yet.
              </p>
            )}
          </div>
        </section>

        {/* --------------- Adopter segments (k-means) --------------- */}
        <section className="card mt-6 p-6 sm:p-8">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="text-bark-900 text-lg font-semibold">
                Adopter segments
              </h2>
              <p className="mt-1 text-sm">
                Adopters grouped by k-means clustering on their profiles. No
                labels are used — the groups and their names come from the data.
              </p>
            </div>
            {segments?.available && (
              <p className="text-stone-neutral shrink-0 text-xs sm:text-right">
                k = {segments.k} · silhouette {segments.silhouette}
                <br />
                {segments.n_adopters} profiles
              </p>
            )}
          </div>

          {!segments ? (
            <div className="py-10">
              <Spinner label="Clustering adopters…" />
            </div>
          ) : !segments.available ? (
            <p className="mt-5 text-sm">
              {segments.reason ??
                'Segmentation is unavailable right now. It needs at least three adopter profiles.'}
            </p>
          ) : (
            <div className="mt-6 grid gap-8 lg:grid-cols-[1.1fr_1fr]">
              <SegmentChart
                data={segments.segments.map((s) => ({
                  ...s,
                  // Full names are long; the list beside the chart spells
                  // each one out in full.
                  short: s.label.replace(/ Households$/, ''),
                }))}
              />

              <ul className="space-y-4">
                {segments.segments.map((s) => (
                  <li key={s.cluster_id} className="border-bark-100 border-l-2 pl-4">
                    <p className="text-bark-900 text-sm font-semibold">
                      {s.label}
                      <span className="text-stone-neutral ml-2 font-normal">
                        {s.count} · {s.share}%
                      </span>
                    </p>
                    <p className="mt-1 text-sm">{s.description}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        {/* --------------- Combined activity feed --------------- */}
        <section className="card mt-6 p-6 sm:p-8">
          <h2 className="text-bark-900 text-lg font-semibold">Recent activity</h2>
          <p className="mt-1 text-sm">
            Volunteer sign-ups and adoption matches, newest first.
          </p>

          {feed.length === 0 ? (
            <p className="mt-6 text-sm">Nothing recorded yet.</p>
          ) : (
            <ol className="divide-bark-100 mt-5 divide-y">
              {feed.map((e) => (
                <li key={`${e.type}-${e.at}-${e.who}`} className="flex gap-4 py-3.5">
                  <span
                    className={`mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-full ${
                      e.type === 'volunteer'
                        ? 'bg-amber-brand/25 text-amber-brand-dark'
                        : 'bg-olive-100 text-olive-700'
                    }`}
                    aria-hidden="true"
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                      <path
                        d={
                          e.type === 'volunteer'
                            ? 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm0 2c-4 0-7 2.2-7 5v1h14v-1c0-2.8-3-5-7-5Z'
                            : 'M12 21s-7.5-4.6-9.6-9A5.4 5.4 0 0 1 12 6.2 5.4 5.4 0 0 1 21.6 12c-2.1 4.4-9.6 9-9.6 9Z'
                        }
                        fill="currentColor"
                      />
                    </svg>
                  </span>

                  <div className="min-w-0 flex-1">
                    <p className="text-bark-900 text-sm font-semibold">
                      {e.who}
                      <span
                        className={`ml-2 rounded-full px-2 py-0.5 text-[11px] font-bold tracking-wide uppercase ${
                          e.type === 'volunteer'
                            ? 'bg-amber-brand/25 text-amber-brand-dark'
                            : 'bg-olive-100 text-olive-700'
                        }`}
                      >
                        {e.type === 'volunteer' ? 'Volunteer' : 'Match'}
                      </span>
                    </p>
                    <p className="mt-0.5 text-sm">{e.detail}</p>
                  </div>

                  {/* Relative for scanning, exact on hover. */}
                  <time
                    dateTime={e.at}
                    title={fmtTime(e.at)}
                    className="shrink-0 text-xs whitespace-nowrap"
                  >
                    {timeAgo(e.at)}
                  </time>
                </li>
              ))}
            </ol>
          )}
        </section>

        {/* --------------- Chatbot activity --------------- */}
        {chatbot && (
          <section className="card mt-6 p-6 sm:p-8">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h2 className="text-bark-900 text-lg font-semibold">
                  FAQ assistant activity
                </h2>
                <p className="mt-1 text-sm">
                  Questions asked of the chatbot and the intent it predicted.
                </p>
              </div>
              <p className="text-stone-neutral shrink-0 text-xs sm:text-right">
                {chatbot.total} question{chatbot.total === 1 ? '' : 's'}
                <br />
                {chatbot.low_confidence} low-confidence
              </p>
            </div>

            {chatbot.total === 0 ? (
              <p className="mt-5 text-sm">
                No one has used the assistant yet.
              </p>
            ) : (
              <div className="mt-6 grid gap-8 lg:grid-cols-2">
                <div>
                  <h3 className="text-bark-900 text-sm font-semibold">
                    Questions by intent
                  </h3>
                  <ul className="mt-3 space-y-2">
                    {chatbot.by_intent.map((row) => {
                      const pct = Math.round((row.count / chatbot.total) * 100)
                      return (
                        <li key={row.intent}>
                          <div className="flex items-center justify-between text-xs">
                            <span className="text-bark-900 font-medium">
                              {INTENT_LABELS[row.intent] ?? row.intent}
                            </span>
                            <span className="tabular-nums">{row.count}</span>
                          </div>
                          <div className="bg-bark-100 mt-1 h-2 overflow-hidden rounded-full">
                            <div
                              className="bg-olive-600 h-full rounded-full"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                </div>

                <div>
                  <h3 className="text-bark-900 text-sm font-semibold">
                    Recent questions
                  </h3>
                  <ul className="divide-bark-100 mt-3 divide-y">
                    {chatbot.recent.map((log) => (
                      <li key={log.id} className="py-2.5">
                        <p className="text-bark-900 text-sm">“{log.question}”</p>
                        <p className="mt-1 flex flex-wrap items-center gap-x-2 text-xs">
                          <span>{INTENT_LABELS[log.predicted_intent] ?? log.predicted_intent}</span>
                          <span aria-hidden="true">·</span>
                          <span className="tabular-nums">
                            {Math.round(log.confidence * 100)}% confident
                          </span>
                          {log.low_confidence && (
                            <span className="bg-amber-brand/25 text-amber-brand-dark rounded-full px-2 py-0.5 font-semibold">
                              fell back
                            </span>
                          )}
                          <span aria-hidden="true">·</span>
                          <span>{timeAgo(log.created_at)}</span>
                        </p>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </section>
        )}

        {/* --------------- Match request detail --------------- */}
        <section className="card mt-6 overflow-hidden">
          <div className="flex flex-col gap-2 p-6 sm:flex-row sm:items-center sm:justify-between sm:p-8 sm:pb-5">
            <div>
              <h2 className="text-bark-900 text-lg font-semibold">
                Match request detail
              </h2>
              <p className="mt-1 text-sm">
                The last {recent.length} adopter profiles submitted.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowTable((v) => !v)}
              className="text-olive-600 hover:bg-olive-50 -mx-3 self-start rounded-lg px-3 py-2 text-sm font-semibold hover:underline sm:self-auto"
            >
              {showTable ? 'Hide chart data table' : 'Show chart data table'}
            </button>
          </div>

          {recent.length === 0 ? (
            <p className="px-6 pb-8 text-sm sm:px-8">Nothing recorded yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="bg-bark-50 text-bark-900 text-xs tracking-wider uppercase">
                  <tr>
                    <Th>When</Th>
                    <Th>User</Th>
                    <Th>Home</Th>
                    <Th>Activity</Th>
                    <Th>Experience</Th>
                    <Th>Kids / pets</Th>
                    <Th>Top match</Th>
                    <Th className="text-right">Score</Th>
                  </tr>
                </thead>
                <tbody className="divide-bark-100 divide-y">
                  {recent.map((r) => (
                    <tr key={r.id} className="hover:bg-bark-50/60">
                      <Td className="tabular-nums whitespace-nowrap">
                        {fmtTime(r.created_at)}
                      </Td>
                      <Td className="text-bark-900 font-medium">{r.user}</Td>
                      <Td>{HOME_LABELS[r.adopter?.home_type] ?? '—'}</Td>
                      <Td className="capitalize">{r.adopter?.activity_level}</Td>
                      <Td className="capitalize">{r.adopter?.experience_level}</Td>
                      <Td>
                        {r.adopter?.has_kids ? 'Kids' : '—'} /{' '}
                        {r.adopter?.has_other_pets ? 'Pets' : '—'}
                      </Td>
                      <Td className="text-bark-900 font-semibold">
                        {r.top_dog ?? '—'}
                      </Td>
                      <Td className="text-right font-bold tabular-nums">
                        {r.top_score != null ? `${r.top_score}%` : '—'}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* --------------- Table view of the chart data --------------- */}
        {showTable && (
          <section className="card mt-6 p-6 sm:p-8">
            <h2 className="text-bark-900 text-lg font-semibold">
              Chart data, as a table
            </h2>
            <div className="mt-4 grid gap-8 sm:grid-cols-2">
              <DataTable
                caption="Activity per day"
                head={['Day', 'Matches', 'Volunteers']}
                rows={activity.map((d) => [d.date, d.requests, d.volunteers])}
              />
              <DataTable
                caption="Times ranked #1"
                head={['Dog', 'Wins']}
                rows={topDogs.map((d) => [d.name, d.wins])}
              />
            </div>
          </section>
        )}
      </div>
    </div>
  )
}

function Th({ children, className = '' }) {
  return <th className={`px-4 py-3 font-semibold sm:px-6 ${className}`}>{children}</th>
}

function Td({ children, className = '' }) {
  return <td className={`px-4 py-3 sm:px-6 ${className}`}>{children}</td>
}

function DataTable({ caption, head, rows }) {
  return (
    <table className="w-full text-left text-sm">
      <caption className="text-bark-900 mb-2 text-left text-sm font-semibold">
        {caption}
      </caption>
      <thead className="text-bark-900 text-xs tracking-wider uppercase">
        <tr>
          {head.map((h, i) => (
            <th key={h} className={`pb-2 ${i ? 'text-right' : ''}`}>
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-bark-100 divide-y">
        {rows.length === 0 && (
          <tr>
            <td colSpan={head.length} className="py-3">
              No data yet.
            </td>
          </tr>
        )}
        {rows.map((r) => (
          <tr key={r[0]}>
            {r.map((cell, i) => (
              <td key={i} className={`py-2 tabular-nums ${i ? 'text-right' : ''}`}>
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
