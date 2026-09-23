import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import AdminTabs from '../components/admin/AdminTabs'
import MedicalTimeline from '../components/medical/MedicalTimeline'
import MlAnomalies from '../components/medical/MlAnomalies'
import ObservationTrends from '../components/medical/ObservationTrends'
import {
  EmptyState,
  ErrorNote,
  RecordStatusPill,
  SeverityBadge,
  StatusPill,
  SuccessNote,
} from '../components/medical/Pills'
import RecordForm from '../components/medical/RecordForm'
import Spinner from '../components/Spinner'
import { api } from '../lib/api'
import {
  CATEGORY_LABEL,
  RECORD_TYPES,
  buildTimeline,
  errorMessage,
  fmtDate,
  fmtDateTime,
  severityStyle,
  timeAgo,
} from '../lib/medical'

/** The evidence behind a finding, shown as plain key/value pairs. */
function Evidence({ evidence }) {
  const entries = Object.entries(evidence ?? {}).filter(
    ([, value]) => value !== null && value !== undefined && typeof value !== 'object',
  )
  if (!entries.length) return null
  return (
    <dl className="text-stone-neutral mt-2 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
      {entries.map(([key, value]) => (
        <div key={key} className="flex gap-2">
          <dt className="font-semibold">{key.replaceAll('_', ' ')}:</dt>
          <dd className="tabular-nums">{String(value)}</dd>
        </div>
      ))}
    </dl>
  )
}

function Section({ title, description, count, onAdd, adding, children }) {
  return (
    <section className="card mt-6 p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-bark-900 text-lg font-semibold">
            {title}
            {count != null && (
              <span className="text-stone-neutral ml-2 text-sm font-normal">{count}</span>
            )}
          </h2>
          {description && <p className="mt-1 text-sm">{description}</p>}
        </div>
        {onAdd && (
          <button
            type="button"
            onClick={onAdd}
            className="bg-bark-50 hover:bg-bark-100 text-bark-900 shrink-0 rounded-full px-4 py-2 text-sm font-semibold"
          >
            {adding ? 'Cancel' : '+ Add'}
          </button>
        )}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  )
}

/** A record row: label, dates, status and notes, stacking on small screens. */
function Row({ title, meta, status, notes }) {
  return (
    <li className="border-bark-100 flex flex-col gap-1 border-b py-3 last:border-0 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
      <div className="min-w-0">
        <p className="text-bark-900 text-sm font-semibold">{title}</p>
        {meta && <p className="text-stone-neutral mt-0.5 text-xs">{meta}</p>}
        {notes && <p className="mt-1 text-sm">{notes}</p>}
      </div>
      {status && <RecordStatusPill status={status} className="shrink-0 self-start" />}
    </li>
  )
}

export default function AdminDogMedical() {
  const { dogId } = useParams()
  const [summary, setSummary] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [alerts, setAlerts] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      // The summary is what the page is built from; the analysis and alerts
      // are fetched alongside it, and a failure in either is reported without
      // emptying the page.
      const [summaryData, analysisData, alertData] = await Promise.all([
        api.medicalSummary(dogId),
        api.healthAnalysis(dogId).catch(() => null),
        api.dogAlerts(dogId).catch(() => null),
      ])
      setSummary(summaryData)
      setAnalysis(analysisData)
      setAlerts(alertData)
      setError('')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [dogId])

  useEffect(() => {
    load()
  }, [load])

  const runAnalysis = async () => {
    setSyncing(true)
    setSyncResult(null)
    try {
      const result = await api.syncAlerts(dogId)
      setSyncResult(result)
      setError('')
      await load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSyncing(false)
    }
  }

  const timeline = useMemo(() => buildTimeline(summary), [summary])

  if (loading && !summary) {
    return (
      <div className="grid min-h-[60vh] place-items-center">
        <Spinner label="Loading medical records…" />
      </div>
    )
  }

  if (error && !summary) {
    return (
      <div className="bg-bark-50 min-h-screen py-10">
        <div className="shell">
          <Link to="/admin/health" className="text-olive-700 text-sm font-semibold">
            ← Back to health monitoring
          </Link>
          <div className="mt-6">
            <ErrorNote onRetry={load}>{error}</ErrorNote>
          </div>
        </div>
      </div>
    )
  }

  const dog = summary.dog
  const risk = analysis ? severityStyle(analysis.risk_level) : null
  const findings = analysis?.findings ?? []
  const qualityFindings = analysis?.data_quality?.findings ?? []
  const activeAlerts = [...(alerts?.open ?? []), ...(alerts?.acknowledged ?? [])]

  return (
    <div className="bg-bark-50 min-h-screen py-10 sm:py-14">
      <div className="shell">
        <header>
          <p className="eyebrow">Admin dashboard</p>
          <h1 className="mt-2 text-3xl sm:text-4xl">{dog.name} — medical record</h1>
          <p className="mt-2 text-sm">
            {dog.age} years · {dog.size} · {dog.temperament}
            {dog.medical_needs && (
              <span className="bg-amber-brand/25 text-amber-brand-dark ml-2 rounded-full px-2 py-0.5 text-[11px] font-bold uppercase">
                Medical needs
              </span>
            )}
          </p>
        </header>

        <AdminTabs />

        <div className="mt-6 flex flex-wrap items-center gap-3">
          <Link to="/admin/health" className="text-olive-700 text-sm font-semibold">
            ← Back to alert queue
          </Link>
          <button
            type="button"
            onClick={runAnalysis}
            disabled={syncing}
            className="bg-olive-500 hover:bg-olive-600 ml-auto rounded-full px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {syncing ? 'Running…' : 'Run health analysis'}
          </button>
        </div>

        {error && (
          <div className="mt-4">
            <ErrorNote onRetry={load}>{error}</ErrorNote>
          </div>
        )}

        {syncResult && (
          <div className="mt-4">
            <SuccessNote>
              Analysis complete — risk {syncResult.risk_level} ({syncResult.risk_score}/100).
              Alerts: {syncResult.created} created, {syncResult.updated} still present,{' '}
              {syncResult.reopened} reopened, {syncResult.resolved} resolved automatically.
            </SuccessNote>
          </div>
        )}

        {/* ---------------------- risk summary ---------------------- */}
        <section className="card mt-6 overflow-hidden">
          {risk && <div className={`h-1.5 w-full ${risk.bar}`} />}
          <div className="grid gap-6 p-5 sm:p-6 lg:grid-cols-[minmax(0,260px)_minmax(0,1fr)]">
            <div>
              <h2 className="text-bark-900 text-lg font-semibold">Health risk summary</h2>
              {analysis ? (
                <>
                  <p className="mt-3 flex items-baseline gap-3">
                    <span className="text-bark-900 text-5xl font-extrabold tabular-nums">
                      {analysis.risk_score}
                    </span>
                    <span className="text-stone-neutral text-sm">/ 100</span>
                  </p>
                  <p className="mt-2">
                    <span
                      className={`inline-flex rounded-full px-3 py-1 text-xs font-bold uppercase ${risk.badge}`}
                    >
                      {risk.label} risk
                    </span>
                  </p>
                  <p className="text-stone-neutral mt-3 text-xs">
                    Generated {timeAgo(analysis.generated_at)} · analysis date{' '}
                    {fmtDate(analysis.analysis_date)}
                  </p>
                  <p className="text-stone-neutral mt-2 text-xs">{analysis.disclaimer}</p>
                </>
              ) : (
                <p className="mt-3 text-sm">The analysis could not be loaded.</p>
              )}
            </div>

            {analysis && (
              <div>
                <h3 className="text-bark-900 text-sm font-semibold">
                  How the score was reached
                </h3>
                {analysis.score_breakdown.points_by_finding.length ? (
                  <>
                    <ul className="mt-2 space-y-1.5">
                      {analysis.score_breakdown.points_by_finding.map((item) => (
                        <li
                          key={item.code}
                          className="flex items-center justify-between gap-3 text-sm"
                        >
                          <span className="min-w-0 truncate">
                            <SeverityBadge severity={item.severity} className="mr-2" />
                            {item.code}
                          </span>
                          <span className="text-bark-900 shrink-0 font-semibold tabular-nums">
                            +{item.points}
                          </span>
                        </li>
                      ))}
                    </ul>
                    <p className="border-bark-100 text-stone-neutral mt-3 border-t pt-2 text-xs">
                      Total {analysis.score_breakdown.total_before_cap}, capped at{' '}
                      {analysis.score_breakdown.max_score}.
                    </p>
                  </>
                ) : (
                  <p className="mt-2 text-sm">
                    No findings, so the score is 0. That reflects what is recorded — it is
                    not a statement that the dog is healthy.
                  </p>
                )}
              </div>
            )}
          </div>
        </section>

        {/* ---------------------- findings ---------------------- */}
        <Section
          title="Health findings"
          description="Patterns in the recorded data that may need attention. Not a diagnosis."
          count={findings.length}
        >
          {findings.length ? (
            <ul className="space-y-3">
              {findings.map((finding) => (
                <li
                  key={finding.code + (finding.evidence?.follow_up_id ?? '')}
                  className="border-bark-100 rounded-xl border p-4"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={finding.severity} />
                    <span className="bg-bark-50 rounded-full px-2.5 py-1 text-[11px] font-semibold">
                      {CATEGORY_LABEL[finding.category] ?? finding.category}
                    </span>
                  </div>
                  <h3 className="text-bark-900 mt-2 text-sm font-semibold">{finding.title}</h3>
                  <p className="mt-1 text-sm">{finding.reason}</p>
                  <Evidence evidence={finding.evidence} />
                  <p className="text-olive-800 bg-olive-50 mt-2 rounded-lg px-3 py-2 text-sm">
                    <span className="font-semibold">Suggested next step: </span>
                    {finding.recommendation}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState>No health findings from the recorded data.</EmptyState>
          )}
        </Section>

        {/* ---------------------- ML anomalies ---------------------- */}
        <Section
          title="AI / ML health anomaly detection"
          description="A model comparing each observation with this dog's own recent history. Separate from the rule-based findings above, and it does not affect the risk score."
          count={analysis?.ml_anomalies?.available ? analysis.ml_anomalies.anomaly_count : null}
        >
          <MlAnomalies ml={analysis?.ml_anomalies} />
        </Section>

        {/* ---------------------- data quality ---------------------- */}
        <Section
          title="Data quality"
          description="Gaps and inconsistencies in the records themselves. Missing information is not a health problem — none of this counts towards the risk score."
          count={qualityFindings.length}
        >
          {analysis && (
            <p className="text-stone-neutral mb-3 text-sm">
              Record completeness:{' '}
              <span className="text-bark-900 font-semibold tabular-nums">
                {analysis.data_quality.score}/100
              </span>
            </p>
          )}
          {qualityFindings.length ? (
            <ul className="space-y-2">
              {qualityFindings.map((item) => (
                <li
                  key={item.code}
                  className="border-bark-100 bg-bark-50/60 rounded-xl border border-dashed p-3"
                >
                  <p className="text-bark-900 text-sm font-semibold">{item.title}</p>
                  <p className="mt-0.5 text-sm">{item.reason}</p>
                  <p className="text-stone-neutral mt-1 text-xs">{item.recommendation}</p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState>The records look complete.</EmptyState>
          )}
        </Section>

        {/* ---------------------- alerts for this dog ---------------------- */}
        <Section
          title="Alerts for this dog"
          description="Findings that have been written down and tracked until resolved."
          count={alerts ? alerts.count : null}
        >
          {!alerts ? (
            <EmptyState>Alerts could not be loaded.</EmptyState>
          ) : !alerts.count ? (
            <EmptyState>
              No alerts yet. Run the health analysis to record the current findings.
            </EmptyState>
          ) : (
            <ul className="space-y-2">
              {[...activeAlerts, ...(alerts.resolved ?? [])].map((alert) => (
                <li
                  key={alert.id}
                  className="border-bark-100 flex flex-wrap items-center gap-2 rounded-xl border p-3"
                >
                  <SeverityBadge severity={alert.severity} />
                  <StatusPill status={alert.status} />
                  <span className="text-bark-900 min-w-0 flex-1 text-sm font-medium">
                    {alert.title}
                  </span>
                  <span className="text-stone-neutral text-xs">
                    {timeAgo(alert.last_detected_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="text-stone-neutral mt-3 text-xs">
            Acknowledge and resolve from the{' '}
            <Link to="/admin/health" className="text-olive-700 underline underline-offset-2">
              alert queue
            </Link>
            .
          </p>
        </Section>

        {/* ---------------------- vaccinations ---------------------- */}
        <Section
          title="Vaccinations"
          description="Status is what was recorded. Whether one is actually due or overdue is worked out by the analysis above, from the dates."
          count={summary.vaccinations.length}
          onAdd={() => setAdding(adding === 'vaccinations' ? null : 'vaccinations')}
          adding={adding === 'vaccinations'}
        >
          {summary.vaccinations.length ? (
            <ul>
              {summary.vaccinations.map((v) => (
                <Row
                  key={v.id}
                  title={v.vaccine_name}
                  meta={[
                    v.administered_date ? `Given ${fmtDate(v.administered_date)}` : 'Not yet given',
                    v.next_due_date ? `next due ${fmtDate(v.next_due_date)}` : 'no due date recorded',
                    v.veterinarian,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                  status={v.status}
                  notes={v.notes}
                />
              ))}
            </ul>
          ) : (
            <EmptyState>No vaccinations recorded.</EmptyState>
          )}
          {adding === 'vaccinations' && (
            <RecordForm
              dogId={dogId}
              kind="vaccinations"
              onSaved={load}
              onCancel={() => setAdding(null)}
            />
          )}
        </Section>

        {/* ---------------------- medications ---------------------- */}
        <Section
          title="Medications"
          count={summary.medications.length}
          onAdd={() => setAdding(adding === 'medications' ? null : 'medications')}
          adding={adding === 'medications'}
        >
          {summary.medications.length ? (
            <ul>
              {summary.medications.map((m) => (
                <Row
                  key={m.id}
                  title={`${m.medication_name} — ${m.dosage}, ${m.frequency}`}
                  meta={[
                    `From ${fmtDate(m.start_date)}`,
                    m.end_date ? `to ${fmtDate(m.end_date)}` : 'ongoing',
                    m.prescribed_by,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                  status={m.status}
                  notes={m.notes}
                />
              ))}
            </ul>
          ) : (
            <EmptyState>No medications recorded.</EmptyState>
          )}
          {adding === 'medications' && (
            <RecordForm
              dogId={dogId}
              kind="medications"
              onSaved={load}
              onCancel={() => setAdding(null)}
            />
          )}
        </Section>

        {/* ---------------------- observations ---------------------- */}
        <Section
          title="Health observations"
          description="Weight, temperature and symptoms over time."
          count={summary.counts.health_observations}
          onAdd={() => setAdding(adding === 'observations' ? null : 'observations')}
          adding={adding === 'observations'}
        >
          <ObservationTrends observations={summary.recent_observations} analysis={analysis} />

          {summary.recent_observations.length ? (
            <ul className="mt-6">
              {summary.recent_observations.map((o) => (
                <Row
                  key={o.id}
                  title={
                    [
                      o.weight_kg != null ? `${o.weight_kg} kg` : null,
                      o.temperature_c != null ? `${o.temperature_c} °C` : null,
                    ]
                      .filter(Boolean)
                      .join(' · ') || 'Observation'
                  }
                  meta={[fmtDate(o.observation_date), (o.symptoms ?? []).join(', ')]
                    .filter(Boolean)
                    .join(' · ')}
                  notes={o.notes}
                />
              ))}
            </ul>
          ) : (
            <div className="mt-6">
              <EmptyState>No observations recorded.</EmptyState>
            </div>
          )}
          {adding === 'observations' && (
            <RecordForm
              dogId={dogId}
              kind="observations"
              onSaved={load}
              onCancel={() => setAdding(null)}
            />
          )}
        </Section>

        {/* ---------------------- follow-ups ---------------------- */}
        <Section
          title="Follow-ups"
          description="Whether one is overdue or due soon is decided by the analysis, not by this list."
          count={summary.follow_ups.length}
          onAdd={() => setAdding(adding === 'follow-ups' ? null : 'follow-ups')}
          adding={adding === 'follow-ups'}
        >
          {summary.follow_ups.length ? (
            <ul>
              {summary.follow_ups.map((f) => (
                <Row
                  key={f.id}
                  title={f.reason}
                  meta={[
                    `Due ${fmtDate(f.due_date)}`,
                    f.completed_date ? `completed ${fmtDate(f.completed_date)}` : null,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                  status={f.status}
                  notes={f.notes}
                />
              ))}
            </ul>
          ) : (
            <EmptyState>No follow-ups recorded.</EmptyState>
          )}
          {adding === 'follow-ups' && (
            <RecordForm
              dogId={dogId}
              kind="follow-ups"
              onSaved={load}
              onCancel={() => setAdding(null)}
            />
          )}
        </Section>

        {/* ---------------------- medical records ---------------------- */}
        <Section
          title="Medical records"
          count={summary.counts.medical_records}
          onAdd={() => setAdding(adding === 'records' ? null : 'records')}
          adding={adding === 'records'}
        >
          {summary.recent_medical_records.length ? (
            <ul>
              {summary.recent_medical_records.map((r) => (
                <Row
                  key={r.id}
                  title={r.title}
                  meta={[fmtDate(r.visit_date), r.record_type, r.veterinarian]
                    .filter(Boolean)
                    .join(' · ')}
                  notes={r.description}
                />
              ))}
            </ul>
          ) : (
            <EmptyState>No medical records yet.</EmptyState>
          )}
          {adding === 'records' && (
            <RecordForm
              dogId={dogId}
              kind="records"
              onSaved={load}
              onCancel={() => setAdding(null)}
            />
          )}
        </Section>

        {/* ---------------------- timeline ---------------------- */}
        <Section
          title="Medical timeline"
          description={`Every record type in date order, newest first. ${
            Object.values(RECORD_TYPES)
              .map((t) => `${t.icon} ${t.label}`)
              .join(' · ')
          }`}
          count={timeline.length}
        >
          <MedicalTimeline entries={timeline} />
        </Section>

        <p className="text-stone-neutral mt-8 text-xs">
          Last loaded {fmtDateTime(new Date().toISOString())}.
        </p>
      </div>
    </div>
  )
}
