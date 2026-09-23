import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import AdminTabs from '../components/admin/AdminTabs'
import {
  EmptyState,
  ErrorNote,
  SeverityBadge,
  StatusPill,
  SuccessNote,
} from '../components/medical/Pills'
import Spinner from '../components/Spinner'
import { api } from '../lib/api'
import {
  CATEGORY_LABEL,
  SEVERITY_ORDER,
  errorMessage,
  fmtDateTime,
  severityStyle,
  timeAgo,
} from '../lib/medical'

const STATUS_FILTERS = [
  { value: '', label: 'All' },
  { value: 'open', label: 'Open' },
  { value: 'acknowledged', label: 'Acknowledged' },
  { value: 'resolved', label: 'Resolved' },
]

/**
 * The alert queue.
 *
 * Filtering is done by the API: every change re-requests with the filters as
 * query parameters, rather than narrowing an already-fetched list, so what is
 * shown is never a subset of a truncated page.
 */
export default function AdminHealth() {
  const [data, setData] = useState(null)
  const [dogs, setDogs] = useState([])
  const [filters, setFilters] = useState({ status: 'open', severity: '', dogId: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState(null)
  const [resolving, setResolving] = useState(null) // alert id with the note box open
  const [note, setNote] = useState('')
  const [flash, setFlash] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const result = await api.adminAlerts({
        status: filters.status || undefined,
        severity: filters.severity || undefined,
        dogId: filters.dogId || undefined,
        limit: 200,
      })
      setData(result)
      setError('')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => {
    load()
  }, [load])

  // The dog filter needs names. A failure here only costs the dropdown, so it
  // must not take the queue down with it.
  useEffect(() => {
    api
      .dogs()
      .then((result) => setDogs(result.dogs ?? []))
      .catch(() => setDogs([]))
  }, [])

  const act = async (alertId, action) => {
    setBusyId(alertId)
    setFlash('')
    try {
      if (action === 'acknowledge') {
        await api.acknowledgeAlert(alertId)
        setFlash('Alert acknowledged.')
      } else {
        await api.resolveAlert(alertId, note.trim() || undefined)
        setFlash('Alert resolved.')
        setResolving(null)
        setNote('')
      }
      setError('')
      await load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusyId(null)
    }
  }

  const totals = data?.totals
  const tiles = totals
    ? [
        { label: 'Open', value: totals.open, tone: 'text-rust' },
        { label: 'Acknowledged', value: totals.acknowledged },
        { label: 'Resolved', value: totals.resolved },
        ...SEVERITY_ORDER.map((name) => ({
          label: `${severityStyle(name).label} (active)`,
          value: totals.active_by_severity?.[name] ?? 0,
        })),
      ]
    : []

  return (
    <div className="bg-bark-50 min-h-screen py-10 sm:py-14">
      <div className="shell">
        <header>
          <p className="eyebrow">Admin dashboard</p>
          <h1 className="mt-2 text-3xl sm:text-4xl">Health monitoring</h1>
          <p className="mt-3 max-w-2xl text-sm">
            Alerts raised by the health analysis from recorded medical data. Every
            alert states the evidence behind it. This is a monitoring aid, not a
            diagnosis.
          </p>
        </header>

        <AdminTabs />

        {/* ------------------------- counts ------------------------- */}
        <section className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          {tiles.map((tile) => (
            <div key={tile.label} className="card p-4">
              <p className="text-xs font-semibold">{tile.label}</p>
              <p
                className={`mt-1 text-2xl font-extrabold tabular-nums ${
                  tile.tone ?? 'text-bark-900'
                }`}
              >
                {tile.value}
              </p>
            </div>
          ))}
          {!totals &&
            Array.from({ length: 7 }).map((_, i) => (
              <div key={i} className="card bg-bark-100/40 h-[76px] animate-pulse p-4" />
            ))}
        </section>

        {/* ------------------------- filters ------------------------- */}
        <section className="card mt-6 p-4 sm:p-5">
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <span className="text-bark-900 block text-sm font-semibold" id="status-label">
                Status
              </span>
              <div
                role="group"
                aria-labelledby="status-label"
                className="mt-2 flex flex-wrap gap-1.5"
              >
                {STATUS_FILTERS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    aria-pressed={filters.status === option.value}
                    onClick={() => setFilters((f) => ({ ...f, status: option.value }))}
                    className={`rounded-full px-3 py-1.5 text-sm font-semibold transition ${
                      filters.status === option.value
                        ? 'bg-olive-500 text-white'
                        : 'bg-bark-50 hover:bg-bark-100'
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label htmlFor="severity" className="text-bark-900 block text-sm font-semibold">
                Severity
              </label>
              <select
                id="severity"
                value={filters.severity}
                onChange={(e) => setFilters((f) => ({ ...f, severity: e.target.value }))}
                className="border-bark-100 focus:border-olive-500 mt-2 w-full rounded-xl border-2 px-3 py-2.5 text-sm outline-none"
              >
                <option value="">Any severity</option>
                {SEVERITY_ORDER.map((name) => (
                  <option key={name} value={name}>
                    {severityStyle(name).label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="dog" className="text-bark-900 block text-sm font-semibold">
                Dog
              </label>
              <select
                id="dog"
                value={filters.dogId}
                onChange={(e) => setFilters((f) => ({ ...f, dogId: e.target.value }))}
                className="border-bark-100 focus:border-olive-500 mt-2 w-full rounded-xl border-2 px-3 py-2.5 text-sm outline-none"
              >
                <option value="">All dogs</option>
                {dogs.map((dog) => (
                  <option key={dog.dog_id} value={dog.dog_id}>
                    {dog.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </section>

        {flash && (
          <div className="mt-4">
            <SuccessNote>{flash}</SuccessNote>
          </div>
        )}
        {error && (
          <div className="mt-4">
            <ErrorNote onRetry={load}>{error}</ErrorNote>
          </div>
        )}

        {/* ------------------------- queue ------------------------- */}
        <section className="mt-6">
          <h2 className="text-bark-900 text-lg font-semibold">
            Alerts{' '}
            {data && (
              <span className="text-stone-neutral text-sm font-normal">
                {data.returned} of {data.count} shown
              </span>
            )}
          </h2>

          {loading && !data ? (
            <div className="py-16">
              <Spinner label="Loading alerts…" />
            </div>
          ) : !data?.alerts.length ? (
            <div className="mt-4">
              <EmptyState>
                No alerts match these filters. Run the health analysis from a dog&rsquo;s
                medical page to check for new findings.
              </EmptyState>
            </div>
          ) : (
            <ul className="mt-4 space-y-3">
              {data.alerts.map((alert) => (
                <li key={alert.id} className="card overflow-hidden">
                  <div className={`h-1 w-full ${severityStyle(alert.severity).bar}`} />
                  <div className="p-4 sm:p-5">
                    <div className="flex flex-wrap items-center gap-2">
                      <SeverityBadge severity={alert.severity} />
                      <StatusPill status={alert.status} />
                      <span className="bg-bark-50 rounded-full px-2.5 py-1 text-[11px] font-semibold">
                        {CATEGORY_LABEL[alert.category] ?? alert.category}
                      </span>
                      <Link
                        to={`/admin/health/dogs/${alert.dog_id}`}
                        className="text-olive-700 ml-auto text-sm font-semibold underline underline-offset-2"
                      >
                        {alert.dog_name ?? `Dog ${alert.dog_id}`}
                      </Link>
                    </div>

                    <h3 className="text-bark-900 mt-3 text-base font-semibold">
                      {alert.title}
                    </h3>
                    <p className="mt-1 text-sm">{alert.reason}</p>
                    {alert.recommendation && (
                      <p className="text-olive-800 bg-olive-50 mt-2 rounded-lg px-3 py-2 text-sm">
                        <span className="font-semibold">Suggested next step: </span>
                        {alert.recommendation}
                      </p>
                    )}

                    <dl className="text-stone-neutral mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
                      <div>
                        <dt className="font-semibold">First detected</dt>
                        <dd title={fmtDateTime(alert.first_detected_at)}>
                          {timeAgo(alert.first_detected_at)}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-semibold">Last detected</dt>
                        <dd title={fmtDateTime(alert.last_detected_at)}>
                          {timeAgo(alert.last_detected_at)}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-semibold">Risk score then</dt>
                        <dd className="tabular-nums">{alert.risk_score_at_detection}</dd>
                      </div>
                      <div>
                        <dt className="font-semibold">Times detected</dt>
                        <dd className="tabular-nums">{alert.detection_count}</dd>
                      </div>
                    </dl>

                    {alert.status === 'resolved' && (
                      <p className="border-bark-100 text-stone-neutral mt-3 border-t pt-3 text-xs">
                        Resolved {timeAgo(alert.resolved_at)}
                        {alert.resolved_by ? ` by ${alert.resolved_by}` : ' automatically'}
                        {alert.resolution_note ? ` — “${alert.resolution_note}”` : ''}
                      </p>
                    )}
                    {alert.acknowledged_at && alert.status !== 'resolved' && (
                      <p className="border-bark-100 text-stone-neutral mt-3 border-t pt-3 text-xs">
                        Acknowledged {timeAgo(alert.acknowledged_at)}
                        {alert.acknowledged_by ? ` by ${alert.acknowledged_by}` : ''}
                      </p>
                    )}

                    {alert.status !== 'resolved' && (
                      <div className="mt-4 flex flex-wrap gap-2">
                        {alert.status === 'open' && (
                          <button
                            type="button"
                            disabled={busyId === alert.id}
                            onClick={() => act(alert.id, 'acknowledge')}
                            className="bg-bark-50 hover:bg-bark-100 text-bark-900 rounded-full px-4 py-2 text-sm font-semibold disabled:opacity-50"
                          >
                            {busyId === alert.id ? 'Working…' : 'Acknowledge'}
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => {
                            setResolving(resolving === alert.id ? null : alert.id)
                            setNote('')
                          }}
                          className="bg-olive-500 hover:bg-olive-600 rounded-full px-4 py-2 text-sm font-semibold text-white"
                        >
                          {resolving === alert.id ? 'Cancel' : 'Resolve'}
                        </button>
                      </div>
                    )}

                    {resolving === alert.id && (
                      <div className="border-bark-100 mt-3 border-t pt-3">
                        <label
                          htmlFor={`note-${alert.id}`}
                          className="text-bark-900 block text-sm font-semibold"
                        >
                          Resolution note <span className="font-normal">(optional)</span>
                        </label>
                        <textarea
                          id={`note-${alert.id}`}
                          rows={2}
                          value={note}
                          maxLength={1000}
                          onChange={(e) => setNote(e.target.value)}
                          placeholder="What was done about it?"
                          className="border-bark-100 focus:border-olive-500 mt-2 w-full rounded-xl border-2 px-3 py-2 text-sm outline-none"
                        />
                        <p className="text-stone-neutral mt-2 text-xs">
                          Resolving keeps the alert as history; it is never deleted. If
                          the finding is still in the data, the next analysis will raise
                          it again.
                        </p>
                        <button
                          type="button"
                          disabled={busyId === alert.id}
                          onClick={() => act(alert.id, 'resolve')}
                          className="bg-olive-500 hover:bg-olive-600 mt-3 rounded-full px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                        >
                          {busyId === alert.id ? 'Saving…' : 'Confirm resolve'}
                        </button>
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}
