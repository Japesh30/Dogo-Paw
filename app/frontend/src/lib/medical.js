// Display helpers for the medical dashboard.
//
// Presentation only. Every judgement — severity, whether a vaccination is
// overdue, what a risk score means — is made by the backend and simply shown
// here. Nothing in this file decides anything clinical.

/** Severity styling, worst first. Colour is never the only signal: each badge
 *  also carries its name in text. */
export const SEVERITY = {
  critical: {
    label: 'Critical',
    badge: 'bg-rust text-white',
    soft: 'bg-rust/10 text-rust-dark',
    bar: 'bg-rust',
    rank: 4,
  },
  high: {
    label: 'High',
    badge: 'bg-rust/85 text-white',
    soft: 'bg-rust/10 text-rust-dark',
    bar: 'bg-rust/85',
    rank: 3,
  },
  moderate: {
    label: 'Moderate',
    badge: 'bg-amber-brand text-bark-900',
    soft: 'bg-amber-brand/25 text-amber-brand-dark',
    bar: 'bg-amber-brand',
    rank: 2,
  },
  low: {
    label: 'Low',
    badge: 'bg-olive-200 text-olive-900',
    soft: 'bg-olive-100 text-olive-700',
    bar: 'bg-olive-400',
    rank: 1,
  },
}

export const SEVERITY_ORDER = ['critical', 'high', 'moderate', 'low']

export const severityStyle = (name) => SEVERITY[name] ?? SEVERITY.low

/** Risk level uses the same scale as severity, so the two read consistently. */
export const RISK_LEVEL = {
  critical: { label: 'Critical', ...SEVERITY.critical },
  high: { label: 'High', ...SEVERITY.high },
  moderate: { label: 'Moderate', ...SEVERITY.moderate },
  low: { label: 'Low', ...SEVERITY.low },
}

/** Alert lifecycle states. */
export const ALERT_STATUS = {
  open: { label: 'Open', chip: 'bg-rust/10 text-rust-dark' },
  acknowledged: { label: 'Acknowledged', chip: 'bg-amber-brand/25 text-amber-brand-dark' },
  resolved: { label: 'Resolved', chip: 'bg-olive-100 text-olive-700' },
}

/** Record statuses, as stored. These are what an admin typed, not a
 *  calculation: a vaccination's real schedule state comes from the analysis. */
export const RECORD_STATUS = {
  completed: 'bg-olive-100 text-olive-700',
  scheduled: 'bg-amber-brand/25 text-amber-brand-dark',
  overdue: 'bg-rust/10 text-rust-dark',
  active: 'bg-olive-100 text-olive-700',
  discontinued: 'bg-bark-100 text-stone-neutral',
  pending: 'bg-amber-brand/25 text-amber-brand-dark',
  missed: 'bg-rust/10 text-rust-dark',
  cancelled: 'bg-bark-100 text-stone-neutral',
}

export const CATEGORY_LABEL = {
  vaccination: 'Vaccination',
  medication: 'Medication',
  follow_up: 'Follow-up',
  weight: 'Weight',
  temperature: 'Temperature',
  medical_record: 'Medical record',
  observation: 'Observation',
  // From the anomaly model rather than a rule; labelled so the queue never
  // presents the two as the same kind of thing.
  ml_anomaly: 'ML anomaly',
}

/** Record types, with the icon and wording used by the timeline. */
export const RECORD_TYPES = {
  records: { label: 'Medical record', icon: '🩺', singular: 'medical record' },
  vaccinations: { label: 'Vaccination', icon: '💉', singular: 'vaccination' },
  medications: { label: 'Medication', icon: '💊', singular: 'medication' },
  observations: { label: 'Health observation', icon: '⚖️', singular: 'observation' },
  'follow-ups': { label: 'Follow-up', icon: '📅', singular: 'follow-up' },
}

export const fmtDate = (value) =>
  value
    ? new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
    : '—'

export const fmtDateTime = (iso) =>
  iso
    ? new Date(iso).toLocaleString(undefined, {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—'

/** "3 days ago" for detection times, which are usually recent. */
export function timeAgo(iso) {
  if (!iso) return '—'
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days} day${days === 1 ? '' : 's'} ago`
  return fmtDateTime(iso)
}

/**
 * What to tell the user when a request fails.
 *
 * The API already sends a plain-English `error` for the cases it knows about,
 * and ApiError carries it. This adds the context that the status code implies
 * and the message alone does not — that a session has expired, or that
 * something changed underneath you. A raw status or stack trace is never shown.
 */
export function errorMessage(err) {
  const detail = err?.message
  switch (err?.status) {
    case 401:
      return 'Your session has expired. Please sign in again.'
    case 403:
      return detail || 'This action needs an admin account.'
    case 404:
      return detail || 'That record no longer exists. It may have been removed.'
    case 409:
      return detail || 'This alert changed before your action was saved. Refresh and try again.'
    case 422:
      return detail || 'Some of the details were not accepted. Check the fields and try again.'
    case 500:
      return 'Something went wrong on the server. Please try again in a moment.'
    default:
      return detail || 'Something went wrong. Please try again.'
  }
}

/** True when the failure means the session is gone rather than the action. */
export const isAuthError = (err) => err?.status === 401

/**
 * One chronological list from every record type, newest first.
 *
 * Built from what the API returned; a medication contributes both its start
 * and, when it has ended, its end. Nothing is inferred beyond that.
 */
export function buildTimeline(summary) {
  if (!summary) return []
  const entries = []

  for (const r of summary.recent_medical_records ?? []) {
    entries.push({
      id: `record-${r.id}`,
      date: r.visit_date,
      kind: 'records',
      title: r.title,
      detail: r.description,
      meta: [r.record_type, r.veterinarian].filter(Boolean).join(' · '),
    })
  }

  for (const v of summary.vaccinations ?? []) {
    if (v.administered_date) {
      entries.push({
        id: `vax-${v.id}`,
        date: v.administered_date,
        kind: 'vaccinations',
        title: `${v.vaccine_name} given`,
        detail: v.notes,
        meta: v.next_due_date ? `Next due ${fmtDate(v.next_due_date)}` : null,
      })
    } else if (v.next_due_date) {
      entries.push({
        id: `vax-due-${v.id}`,
        date: v.next_due_date,
        kind: 'vaccinations',
        title: `${v.vaccine_name} due`,
        detail: v.notes,
        meta: v.status,
        upcoming: true,
      })
    }
  }

  for (const m of summary.medications ?? []) {
    entries.push({
      id: `med-start-${m.id}`,
      date: m.start_date,
      kind: 'medications',
      title: `${m.medication_name} started`,
      detail: [m.dosage, m.frequency].filter(Boolean).join(', '),
      meta: m.prescribed_by,
    })
    if (m.end_date) {
      entries.push({
        id: `med-end-${m.id}`,
        date: m.end_date,
        kind: 'medications',
        title: `${m.medication_name} ${m.status === 'discontinued' ? 'discontinued' : 'ended'}`,
        detail: m.notes,
      })
    }
  }

  for (const o of summary.recent_observations ?? []) {
    const bits = []
    if (o.weight_kg != null) bits.push(`${o.weight_kg} kg`)
    if (o.temperature_c != null) bits.push(`${o.temperature_c} °C`)
    entries.push({
      id: `obs-${o.id}`,
      date: o.observation_date,
      kind: 'observations',
      title: bits.join(' · ') || 'Observation recorded',
      detail: o.notes,
      meta: (o.symptoms ?? []).join(', '),
    })
  }

  for (const f of summary.follow_ups ?? []) {
    entries.push({
      id: `fup-${f.id}`,
      date: f.completed_date ?? f.due_date,
      kind: 'follow-ups',
      title: `${f.status === 'completed' ? 'Completed' : 'Due'}: ${f.reason}`,
      detail: f.notes,
      meta: f.status,
      upcoming: f.status === 'pending' && !f.completed_date,
    })
  }

  return entries
    .filter((e) => e.date)
    .sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0))
}
